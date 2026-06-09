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
from aoa.brokerage.models import Account, AssetClass, Position, Side
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

        # Running tallies for book-level checks.
        buy_notional = 0.0
        options_notional = sum(
            abs(p.market_value) for p in positions if p.asset_class is AssetClass.OPTION
        )
        approved_count = 0
        min_cash = self.limits.min_cash_buffer_pct * account.equity

        for prop in proposals:
            notes: list[str] = []
            ok = True

            if kill:
                prop.approved = False
                prop.risk_notes = [
                    f"Daily loss kill-switch active (P/L {daily_pl:.2f} ≤ "
                    f"limit {loss_limit:.2f}); no new risk."
                ]
                # Allow exits even under kill switch.
                if not _is_exit(prop, pos_by_symbol):
                    continue

            # --- Cash-account structural rules ------------------------------
            if prop.side is Side.SELL and not _is_exit(prop, pos_by_symbol):
                if prop.asset_class is AssetClass.EQUITY:
                    ok = False
                    notes.append("Rejected: opening equity short not allowed in a cash account.")
                else:
                    # Opening option sells must be covered/cash-secured. We can only
                    # verify a covered call (long >=100 shares of the underlying).
                    if not _is_covered_short_option(prop, pos_by_symbol):
                        ok = False
                        notes.append(
                            "Rejected: uncovered short option not allowed in a cash account."
                        )

            # --- Per-cycle order cap ----------------------------------------
            if ok and approved_count >= self.limits.max_orders_per_cycle:
                ok = False
                notes.append(
                    f"Rejected: per-cycle order cap reached "
                    f"({self.limits.max_orders_per_cycle})."
                )

            # --- Sizing checks (only for opening buys) ----------------------
            if ok and prop.side is Side.BUY:
                notional = prop.est_notional
                # Per-position cap.
                pos_cap = self.limits.max_position_pct * account.equity
                if notional > pos_cap:
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

            prop.approved = ok
            prop.risk_notes = notes or (["OK"] if ok else ["Rejected."])
            if ok:
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
