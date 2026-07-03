"""Pipeline stages — composable steps extracted from the monolithic orchestrator."""

from __future__ import annotations

import math
from dataclasses import dataclass

from aoa.agents.base import Direction, Signal, TradeProposal
from aoa.brokerage.models import AssetClass, Side
from aoa.swarm.context import CycleContext
from aoa.swarm.pipeline import PipelineStage


@dataclass
class IntakeStage(PipelineStage):
    """Pull account state, resolve universe, build market snapshots."""

    name: str = "intake"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        ctx.market.clear_cache()

        bb.account = ctx.broker.get_account()
        bb.positions = ctx.broker.get_positions()
        ctx.update_starting_equity(bb.account.equity)
        ctx.journal.record(
            "cycle.start",
            {
                "mode": ctx.config.trading_mode,
                "equity": bb.account.equity,
                "settled_cash": bb.account.settled_cash,
                "starting_equity": ctx.starting_equity,
                "n_positions": len(bb.positions),
            },
        )

        if ctx.config.universe:
            bb.universe = list(ctx.config.universe)
        else:
            bb.universe = ctx.broker.get_most_active(limit=25)

        if not bb.universe:
            ctx.notes.append("Empty universe — nothing to analyze.")
            return False

        bb.snapshots = ctx.market.snapshots(bb.universe)
        return True


@dataclass
class ScanStage(PipelineStage):
    """Scanner shortlists candidates from the universe."""

    name: str = "scan"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        bb.candidates = ctx.agents.scanner.scan(
            bb.snapshots, max_candidates=ctx.max_candidates
        )
        ctx.journal.record("scanner.candidates", {"candidates": bb.candidates})
        if not bb.candidates:
            ctx.notes.append("Scanner returned no candidates.")
        return True


@dataclass
class AnalyzeStage(PipelineStage):
    """Per-candidate technical + fundamental analysis and options ideas."""

    name: str = "analyze"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        per_symbol: list[dict] = []
        for cand in bb.candidates:
            per_symbol.append(_analyze_one(ctx, cand))
        bb.per_symbol = per_symbol
        return True


@dataclass
class PortfolioStage(PipelineStage):
    """Portfolio manager synthesizes signals into target trades."""

    name: str = "portfolio"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
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
        pm = ctx.agents.portfolio.decide(
            bb.per_symbol,
            positions_ctx,
            account_ctx,
            max_new_positions=ctx.config.risk.max_orders_per_cycle,
        )
        bb.commentary = pm.get("portfolio_commentary", "")
        ctx.journal.record(
            "portfolio.decision",
            {"proposals": pm.get("proposals", []), "commentary": bb.commentary},
        )
        ctx.pm_raw = pm
        return True


@dataclass
class MaterializeStage(PipelineStage):
    """Convert PM dollar targets into share/contract proposals."""

    name: str = "materialize"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        raw = (ctx.pm_raw or {}).get("proposals", [])
        bb.proposals = _materialize_proposals(raw, bb)
        return True


@dataclass
class RiskStage(PipelineStage):
    """Deterministic guards + LLM veto."""

    name: str = "risk"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        ctx.agents.risk.review(
            bb.proposals,
            bb.account,
            bb.positions,
            starting_equity=ctx.starting_equity,
        )
        ctx.journal.record(
            "risk.review",
            {"proposals": [p.to_context() for p in bb.proposals]},
        )
        return True


@dataclass
class ExecuteStage(PipelineStage):
    """Submit approved trades (or simulate in dry-run)."""

    name: str = "execute"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        ctx.execution = ctx.executor.execute(bb.proposals)
        ctx.journal.record(
            "cycle.end",
            {
                "submitted": len(ctx.execution.submitted),
                "skipped": len(ctx.execution.skipped),
                "errors": len(ctx.execution.errors),
                "dry_run": ctx.execution.dry_run,
            },
        )
        return True


def default_stages() -> list[PipelineStage]:
    return [
        IntakeStage(),
        ScanStage(),
        AnalyzeStage(),
        PortfolioStage(),
        MaterializeStage(),
        RiskStage(),
        ExecuteStage(),
    ]


# ----------------------------------------------------------------- analysis
def _analyze_one(ctx: CycleContext, cand: dict) -> dict:
    bb = ctx.blackboard
    symbol = cand.get("symbol", "").upper()
    snap = bb.snapshots.get(symbol) or ctx.market.snapshot(symbol)

    tech = ctx.agents.technical.analyze(snap)
    fund = ctx.agents.fundamental.analyze(snap)
    bb.add_signal(tech)
    bb.add_signal(fund)

    entry: dict = {
        "symbol": symbol,
        "scanner_reason": cand.get("reason", ""),
        "signals": [tech.to_context(), fund.to_context()],
    }

    combined_dir, combined_conv = _combine(tech, fund)
    price = (snap.quote.mid if snap.quote else None) or (
        snap.technicals.get("last_close") if snap.technicals else None
    )
    if (
        combined_dir is not Direction.NEUTRAL
        and combined_conv >= 0.55
        and price
        and bb.account
        and bb.account.options_level >= 1
    ):
        idea = ctx.agents.options.propose(symbol, combined_dir, combined_conv, price)
        if idea:
            contract = idea.pop("_contract", None)
            if contract is not None:
                bb.option_contracts[contract.symbol] = contract
            bb.options_ideas[symbol] = idea
            entry["options_idea"] = {
                k: v for k, v in idea.items() if not k.startswith("_")
            }
    return entry


def _combine(tech: Signal, fund: Signal) -> tuple[Direction, float]:
    """Combine technical & fundamental signals into a single directional view."""
    if tech.direction == fund.direction and tech.direction is not Direction.NEUTRAL:
        return tech.direction, min(1.0, (tech.conviction + fund.conviction) / 1.6)
    if tech.direction is not Direction.NEUTRAL:
        return tech.direction, tech.conviction * 0.6
    return Direction.NEUTRAL, 0.0


def _materialize_proposals(raw: list[dict], bb) -> list[TradeProposal]:
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
                continue
            price = contract.mid
            if price <= 0:
                continue
            qty = max(1, math.floor(target / (price * 100))) if side is Side.BUY else 1
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


def _marketable_limit(price: float, side: Side) -> float:
    pad = 1.01 if side is Side.BUY else 0.99
    return round(price * pad, 2)
