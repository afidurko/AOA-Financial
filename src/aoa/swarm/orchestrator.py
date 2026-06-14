"""The orchestrator — runs one full analysis→decision→execution cycle.

Pipeline per cycle:

1. Pull account + positions (broker = information source).
2. Resolve the trading universe (config list or broker's most-actives).
3. Build market-data snapshots (quotes, bars, indicators).
4. Scanner shortlists candidates.
5. Technical + fundamental agents emit signals per candidate.
6. Options strategist proposes structures where conviction is directional.
7. Portfolio manager synthesizes everything into target trades.
8. Convert targets to share/contract quantities.
9. Risk manager (deterministic guards + LLM veto) vets the batch.
10. Executor submits approved trades (or simulates in dry-run).
11. Everything is journaled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from aoa.adapt.signal_adapter import SignalAdapter
from aoa.agents.base import Direction, Signal, TradeProposal
from aoa.agents.fundamental import FundamentalAgent
from aoa.agents.options import OptionsStrategistAgent
from aoa.agents.portfolio import PortfolioManagerAgent
from aoa.agents.risk import RiskManagerAgent
from aoa.agents.scanner import ScannerAgent
from aoa.agents.technical import TechnicalAgent
from aoa.brokerage.base import Broker
from aoa.brokerage.models import AssetClass, Side
from aoa.config import Config
from aoa.data.market_data import MarketDataService
from aoa.execution.executor import ExecutionReport, Executor
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient
from aoa.swarm.blackboard import Blackboard


@dataclass
class CycleResult:
    blackboard: Blackboard
    execution: ExecutionReport | None = None
    notes: list[str] = field(default_factory=list)


class Orchestrator:
    def __init__(
        self,
        config: Config,
        broker: Broker,
        llm: LLMClient,
        journal: Journal | None = None,
        signal_adapter: SignalAdapter | None = None,
    ) -> None:
        self.config = config
        self.broker = broker
        self.llm = llm
        self.journal = journal or Journal()
        self.market = MarketDataService(broker)

        # Optional low-rank online adaptation of agent signals. When present,
        # raw agent convictions are recalibrated before they flow downstream,
        # and learned across cycles from each symbol's realized return.
        self.signal_adapter = signal_adapter
        self._adapt_pending: dict[str, dict] = {}

        # Agents.
        self.scanner = ScannerAgent(llm)
        self.technical = TechnicalAgent(llm)
        self.fundamental = FundamentalAgent(llm)
        self.options = OptionsStrategistAgent(llm, broker)
        self.portfolio = PortfolioManagerAgent(llm)
        self.risk = RiskManagerAgent(llm, config.risk)
        self.executor = Executor(broker, self.journal, dry_run=config.dry_run)

        # Daily-loss tracking.
        self._equity_day: date | None = None
        self._starting_equity: float = 0.0

    # ------------------------------------------------------------------ cycle
    def run_cycle(self, *, max_candidates: int = 6) -> CycleResult:
        bb = Blackboard()
        notes: list[str] = []
        self.market.clear_cache()

        # 1) Account & positions.
        bb.account = self.broker.get_account()
        bb.positions = self.broker.get_positions()
        self._update_starting_equity(bb.account.equity)
        self.journal.record(
            "cycle.start",
            {
                "mode": self.config.trading_mode,
                "equity": bb.account.equity,
                "settled_cash": bb.account.settled_cash,
                "starting_equity": self._starting_equity,
                "n_positions": len(bb.positions),
            },
        )

        # 2) Universe.
        bb.universe = self._resolve_universe()
        if not bb.universe:
            notes.append("Empty universe — nothing to analyze.")
            return CycleResult(blackboard=bb, notes=notes)

        # 3) Snapshots.
        bb.snapshots = self.market.snapshots(bb.universe)

        # 4) Scan.
        bb.candidates = self.scanner.scan(bb.snapshots, max_candidates=max_candidates)
        self.journal.record("scanner.candidates", {"candidates": bb.candidates})
        if not bb.candidates:
            notes.append("Scanner returned no candidates.")
            # Still run the PM on existing positions to consider exits.

        # 5 & 6) Per-candidate analysis.
        per_symbol = self._analyze_candidates(bb)

        # 7) Portfolio decision.
        account_ctx = {
            "equity": bb.account.equity,
            "settled_cash": bb.account.settled_cash,
            "buying_power": bb.account.buying_power,
            "options_level": bb.account.options_level,
        }
        positions_ctx = [
            {
                "symbol": p.symbol,
                "asset_class": p.asset_class.value,
                "qty": p.qty,
                "avg_entry_price": p.avg_entry_price,
                "market_value": p.market_value,
                "unrealized_pl": p.unrealized_pl,
            }
            for p in bb.positions
        ]
        pm = self.portfolio.decide(
            per_symbol,
            positions_ctx,
            account_ctx,
            max_new_positions=self.config.risk.max_orders_per_cycle,
        )
        bb.commentary = pm.get("portfolio_commentary", "")
        self.journal.record(
            "portfolio.decision",
            {"proposals": pm.get("proposals", []), "commentary": bb.commentary},
        )

        # 8) Convert to concrete proposals.
        bb.proposals = self._materialize_proposals(pm.get("proposals", []), bb)

        # 9) Risk review.
        self.risk.review(
            bb.proposals,
            bb.account,
            bb.positions,
            starting_equity=self._starting_equity,
        )
        self.journal.record(
            "risk.review",
            {"proposals": [p.to_context() for p in bb.proposals]},
        )

        # 10) Execute.
        report = self.executor.execute(bb.proposals)
        self.journal.record(
            "cycle.end",
            {
                "submitted": len(report.submitted),
                "skipped": len(report.skipped),
                "errors": len(report.errors),
                "dry_run": report.dry_run,
            },
        )
        return CycleResult(blackboard=bb, execution=report, notes=notes)

    # --------------------------------------------------------------- helpers
    def _update_starting_equity(self, equity: float) -> None:
        today = date.today()
        if self._equity_day != today:
            self._equity_day = today
            self._starting_equity = equity

    def _resolve_universe(self) -> list[str]:
        if self.config.universe:
            return list(self.config.universe)
        active = self.broker.get_most_active(limit=25)
        return active

    def _analyze_candidates(self, bb: Blackboard) -> list[dict]:
        per_symbol: list[dict] = []
        new_pending: dict[str, dict] = {}
        n_learned = 0
        n_adapted = 0
        for cand in bb.candidates:
            symbol = cand.get("symbol", "").upper()
            snap = bb.snapshots.get(symbol) or self.market.snapshot(symbol)
            price = (snap.quote.mid if snap.quote else None) or (
                snap.technicals.get("last_close") if snap.technicals else None
            )

            tech = self.technical.analyze(snap)
            fund = self.fundamental.analyze(snap)

            # Low-rank adaptation: learn from last cycle's call, then recalibrate.
            if self.signal_adapter is not None:
                n_learned += self._learn_from_prior(symbol, price)
                # Remember this cycle's *raw* signals to score next time.
                if price:
                    new_pending[symbol] = {
                        "price": price,
                        "signals": [_pending_entry(tech), _pending_entry(fund)],
                    }
                tech = self.signal_adapter.adapt_signal(tech)
                fund = self.signal_adapter.adapt_signal(fund)
                n_adapted += sum("adapted" in s.tags for s in (tech, fund))

            bb.add_signal(tech)
            bb.add_signal(fund)

            entry: dict = {
                "symbol": symbol,
                "scanner_reason": cand.get("reason", ""),
                "signals": [tech.to_context(), fund.to_context()],
            }

            # Options idea when there is a corroborated directional view.
            combined_dir, combined_conv = _combine(tech, fund)
            if (
                combined_dir is not Direction.NEUTRAL
                and combined_conv >= 0.55
                and price
                and bb.account
                and bb.account.options_level >= 1
            ):
                idea = self.options.propose(symbol, combined_dir, combined_conv, price)
                if idea:
                    contract = idea.pop("_contract", None)
                    if contract is not None:
                        bb.option_contracts[contract.symbol] = contract
                    bb.options_ideas[symbol] = idea
                    entry["options_idea"] = {
                        k: v for k, v in idea.items() if not k.startswith("_")
                    }
            per_symbol.append(entry)

        if self.signal_adapter is not None:
            self._adapt_pending = new_pending
            self.journal.record(
                "adapt.applied",
                {
                    "signals_adapted": n_adapted,
                    "outcomes_learned": n_learned,
                    "total_updates": self.signal_adapter.updates,
                },
            )
        return per_symbol

    def _learn_from_prior(self, symbol: str, price: float | None) -> int:
        """Score the previous cycle's signals for ``symbol`` against the realized
        return implied by the price move, and update the adapter. Returns the
        number of outcomes learned from."""
        prior = self._adapt_pending.get(symbol)
        if not prior or not price or not prior.get("price"):
            return 0
        realized = (price - prior["price"]) / prior["price"]
        learned = 0
        for s in prior["signals"]:
            self.signal_adapter.record_outcome(
                agent=s["agent"],
                direction=s["direction"],
                conviction=s["conviction"],
                realized_return=realized,
                horizon=s["horizon"],
            )
            learned += 1
        return learned

    def _materialize_proposals(self, raw: list[dict], bb: Blackboard) -> list[TradeProposal]:
        proposals: list[TradeProposal] = []
        pos_by_symbol = {p.symbol: p for p in bb.positions}
        for item in raw:
            symbol = item.get("symbol", "").upper()
            instrument = item.get("instrument", "equity")
            side = Side(item.get("side", "buy"))
            target = float(item.get("target_notional", 0) or 0)
            if target <= 0 and side is Side.BUY:
                continue

            if instrument == "option":
                contract = bb.option_contracts.get(symbol)
                if contract is None:
                    continue  # PM referenced an option we didn't surface — skip.
                price = contract.mid
                if price <= 0:
                    continue
                qty = max(1, math.floor(target / (price * 100))) if side is Side.BUY else 1
                # For an option sell, clamp to an existing position if any.
                pos = pos_by_symbol.get(symbol)
                if side is Side.SELL and pos is not None:
                    qty = int(abs(pos.qty))
                proposals.append(
                    TradeProposal(
                        symbol=symbol,
                        asset_class=AssetClass.OPTION,
                        side=side,
                        qty=qty,
                        underlying=contract.underlying,
                        strategy=item.get("strategy", "option"),
                        conviction=float(item.get("conviction", 0.5)),
                        rationale=item.get("rationale", ""),
                        est_price=price,
                        limit_price=_marketable_limit(price, side),
                    )
                )
            else:
                snap = bb.snapshots.get(symbol)
                price = (snap.quote.mid if snap and snap.quote else None) or (
                    snap.technicals.get("last_close") if snap and snap.technicals else None
                )
                if not price or price <= 0:
                    continue
                pos = pos_by_symbol.get(symbol)
                if side is Side.SELL:
                    # Exit/trim: never sell more than we hold (cash account).
                    held = pos.qty if pos else 0
                    qty = min(math.floor(target / price), held) if target > 0 else held
                    qty = int(max(0, qty))
                    if qty <= 0:
                        continue
                else:
                    qty = math.floor(target / price)
                    if qty <= 0:
                        continue
                proposals.append(
                    TradeProposal(
                        symbol=symbol,
                        asset_class=AssetClass.EQUITY,
                        side=side,
                        qty=qty,
                        strategy=item.get("strategy", "long_equity"),
                        conviction=float(item.get("conviction", 0.5)),
                        rationale=item.get("rationale", ""),
                        est_price=price,
                        limit_price=_marketable_limit(price, side),
                    )
                )
        return proposals


def _pending_entry(signal: Signal) -> dict:
    """The minimal record of a raw signal needed to score it next cycle."""
    return {
        "agent": signal.source,
        "direction": signal.direction.value,
        "conviction": signal.conviction,
        "horizon": signal.horizon,
    }


def _combine(tech: Signal, fund: Signal) -> tuple[Direction, float]:
    """Combine technical & fundamental signals into a single directional view."""
    if tech.direction == fund.direction and tech.direction is not Direction.NEUTRAL:
        return tech.direction, min(1.0, (tech.conviction + fund.conviction) / 1.6)
    # Technicals lead when they disagree, but conviction is discounted.
    if tech.direction is not Direction.NEUTRAL:
        return tech.direction, tech.conviction * 0.6
    return Direction.NEUTRAL, 0.0


def _marketable_limit(price: float, side: Side) -> float:
    """A protective limit ~1% through the mid to improve fill odds without chasing."""
    pad = 1.01 if side is Side.BUY else 0.99
    return round(price * pad, 2)
