"""Deterministic, non-negotiable risk guardrails.

These are pure functions of the proposal, the account, and the configured limits
— no LLM involved. They are the last line of defense and enforce the invariants
of a *cash account*:

- No shorting equities (a sell is only allowed to close an existing long).
- No naked short options (only covered/cash-secured shorts; we conservatively
  reject any opening option sell unless explicitly covered).
- Per-position and per-book size caps.
- A minimum settled-cash buffer.
- A daily-loss kill switch.
- A hard cap on aggregate buy notional vs. settled cash.
- A per-cycle order count cap.
"""

from __future__ import annotations

from dataclasses import dataclass

from aoa.agents.base import TradeProposal
from aoa.brokerage.models import Account, AssetClass, OptionType, Position, Side
from aoa.config import RiskLimits


@dataclass
class GuardDecision:
    approved: bool
    reasons: list[str]


class RiskGuards:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def evaluate_cycle(
        self,
        proposals: list[TradeProposal],
        account: Account,
        positions: list[Position],
        *,
        starting_equity: float,
    ) -> list[TradeProposal]:
        """Vet a batch of proposals together (so we can enforce book-level caps).

        Mutates each proposal's ``approved`` / ``risk_notes`` and returns the list.
        """
        pos_by_symbol = {p.symbol: p for p in positions}

        # --- Kill switch: daily loss limit ----------------------------------
        daily_pl = (account.equity - starting_equity) if starting_equity else 0.0
        loss_limit = -abs(self.limits.max_daily_loss_pct) * (starting_equity or account.equity)
        kill = starting_equity > 0 and daily_pl <= loss_limit
        kill_note = (
            f"Daily loss kill-switch active (P/L {daily_pl:.2f} ≤ limit {loss_limit:.2f}); "
            "no new risk."
        )

        # Running tallies for book-level checks.
        buy_notional = 0.0
        options_notional = sum(
            abs(p.market_value) for p in positions if p.asset_class is AssetClass.OPTION
        )
        # Existing + in-cycle equity exposure per symbol (for per-position cap).
        equity_exposure: dict[str, float] = {
            p.symbol: abs(p.market_value)
            for p in positions
            if p.asset_class is AssetClass.EQUITY and p.qty > 0
        }
        approved_count = 0
        min_cash = self.limits.min_cash_buffer_pct * account.equity
        pos_cap = self.limits.max_position_pct * account.equity

        for prop in proposals:
            notes: list[str] = []
            ok = True
            is_exit = _is_exit(prop, pos_by_symbol)

            if kill:
                if not is_exit:
                    prop.approved = False
                    prop.risk_notes = [kill_note]
                    continue
                notes.append(f"{kill_note} Exit allowed.")

            # --- Cash-account structural rules ------------------------------
            if prop.side is Side.SELL and not is_exit:
                if prop.asset_class is AssetClass.EQUITY:
                    ok = False
                    notes.append("Rejected: opening equity short not allowed in a cash account.")
                elif not _is_permitted_short_option(prop, pos_by_symbol, account):
                    ok = False
                    notes.append(
                        "Rejected: uncovered short option not allowed in a cash account."
                    )

            # --- Per-cycle order cap (opening risk only; exits are exempt) --
            if ok and not is_exit and approved_count >= self.limits.max_orders_per_cycle:
                ok = False
                notes.append(
                    f"Rejected: per-cycle order cap reached "
                    f"({self.limits.max_orders_per_cycle})."
                )

            # --- Sizing checks (only for opening buys) ----------------------
            if ok and prop.side is Side.BUY:
                notional = prop.est_notional
                # Per-position cap includes existing holdings and same-cycle buys.
                if prop.asset_class is AssetClass.EQUITY:
                    projected = equity_exposure.get(prop.symbol, 0.0) + notional
                    if projected > pos_cap:
                        ok = False
                        notes.append(
                            f"Rejected: projected position notional {projected:.0f} "
                            f"exceeds per-position cap {pos_cap:.0f} "
                            f"({self.limits.max_position_pct:.0%} of equity)."
                        )
                elif notional > pos_cap:
                    ok = False
                    notes.append(
                        f"Rejected: position notional {notional:.0f} exceeds per-position "
                        f"cap {pos_cap:.0f} ({self.limits.max_position_pct:.0%} of equity)."
                    )
                # Options book cap.
                if ok and prop.asset_class is AssetClass.OPTION:
                    opt_cap = self.limits.max_options_pct * account.equity
                    if options_notional + notional > opt_cap:
                        ok = False
                        notes.append(
                            f"Rejected: options premium {options_notional + notional:.0f} would "
                            f"exceed options book cap {opt_cap:.0f}."
                        )
                # Settled-cash + buffer check (aggregate across the cycle).
                if ok:
                    projected_cash = account.settled_cash - buy_notional - notional
                    if projected_cash < min_cash:
                        ok = False
                        notes.append(
                            f"Rejected: buy would breach minimum cash buffer "
                            f"(projected settled cash {projected_cash:.0f} < "
                            f"{min_cash:.0f})."
                        )
                if ok:
                    buy_notional += notional
                    if prop.asset_class is AssetClass.OPTION:
                        options_notional += notional
                    elif prop.asset_class is AssetClass.EQUITY:
                        equity_exposure[prop.symbol] = (
                            equity_exposure.get(prop.symbol, 0.0) + notional
                        )

            prop.approved = ok
            prop.risk_notes = notes or (["OK"] if ok else ["Rejected."])
            if ok and not is_exit:
                approved_count += 1

        return proposals


def _is_exit(prop: TradeProposal, pos_by_symbol: dict[str, Position]) -> bool:
    """A sell that reduces/closes an existing long of the same symbol."""
    pos = pos_by_symbol.get(prop.symbol)
    return (
        prop.side is Side.SELL
        and pos is not None
        and pos.qty > 0
        and prop.qty <= pos.qty + 1e-9
    )


def _is_covered_short_option(prop: TradeProposal, pos_by_symbol: dict[str, Position]) -> bool:
    """Approximate covered-call check: long >= 100 shares per contract of the underlying."""
    if prop.underlying is None:
        return False
    equity_pos = pos_by_symbol.get(prop.underlying)
    if equity_pos is None or equity_pos.qty <= 0:
        return False
    return equity_pos.qty >= abs(prop.qty) * 100


def _is_cash_secured_put(
    prop: TradeProposal, account: Account, *, contracts: float
) -> bool:
    """Cash-secured put: settled cash must cover strike × 100 × contracts."""
    parsed = _parse_occ(prop.symbol)
    if parsed is None:
        return False
    otype, strike, _ = parsed
    if otype is not OptionType.PUT:
        return False
    collateral = strike * 100 * abs(contracts)
    return account.settled_cash >= collateral


def _is_permitted_short_option(
    prop: TradeProposal,
    pos_by_symbol: dict[str, Position],
    account: Account,
) -> bool:
    """Opening option sell allowed only if covered call or cash-secured put."""
    if _is_covered_short_option(prop, pos_by_symbol):
        return True
    return _is_cash_secured_put(prop, account, contracts=prop.qty)


def _parse_occ(symbol: str) -> tuple[OptionType, float, str] | None:
    """Parse OCC tail: YYMMDD + C/P + strike×1000 (8 digits)."""
    if len(symbol) < 15:
        return None
    tail = symbol[-15:]
    date_part, type_char, strike_part = tail[:6], tail[6], tail[7:]
    if type_char not in ("C", "P") or not date_part.isdigit() or not strike_part.isdigit():
        return None
    strike = int(strike_part) / 1000.0
    otype = OptionType.CALL if type_char == "C" else OptionType.PUT
    return otype, strike, date_part
