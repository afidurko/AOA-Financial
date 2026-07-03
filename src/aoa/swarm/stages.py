"""Pipeline stages — composable steps extracted from the monolithic orchestrator."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from aoa.agents.base import Direction, TradeProposal
from aoa.brokerage.models import AssetClass, Side
from aoa.data.market_data import SymbolSnapshot
from aoa.execution.pricing import marketable_limit
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
        bb.environment.global_context = {
            "mode": ctx.config.trading_mode,
            "universe_size": len(bb.universe),
        }
        return True


@dataclass
class ScanStage(PipelineStage):
    """Scanner shortlists candidates from the universe."""

    name: str = "scan"
    checkpoint: bool = True

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        bb.candidates = ctx.agents.scanner.scan(
            bb.snapshots, max_candidates=ctx.max_candidates
        )
        ctx.journal.record("scanner.candidates", {"candidates": bb.candidates})
        bb.events.emit("domain.write", "scanner", {"candidates": len(bb.candidates)})

        bb.environment.set_domain(
            "scanner",
            {
                "candidates": bb.candidates,
                "by_symbol": {
                    c.get("symbol", "").upper(): c for c in bb.candidates if c.get("symbol")
                },
            },
        )
        bb.environment.global_context["n_candidates"] = len(bb.candidates)

        if not bb.candidates:
            ctx.notes.append("Scanner returned no candidates.")
        return True


@dataclass
class AnalyzeStage(PipelineStage):
    """Per-candidate technical + fundamental analysis, meshing, and options."""

    name: str = "analyze"
    checkpoint: bool = True

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        symbols = [c.get("symbol", "").upper() for c in bb.candidates if c.get("symbol")]
        if ctx.config.news_enabled and symbols:
            ctx.news_by_symbol = ctx.news.headlines(symbols, limit=5)
            ctx.journal.record(
                "news.fetched",
                {
                    "symbols": symbols,
                    "counts": {sym: len(items) for sym, items in ctx.news_by_symbol.items()},
                },
            )
        else:
            ctx.news_by_symbol = {}

        workers = max(1, ctx.config.parallel_workers)
        if workers == 1 or len(ctx.blackboard.candidates) <= 1:
            for cand in ctx.blackboard.candidates:
                _analyze_one(ctx, cand)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_analyze_one, ctx, cand) for cand in ctx.blackboard.candidates
                ]
                for fut in as_completed(futures):
                    fut.result()
        return True


@dataclass
class PortfolioStage(PipelineStage):
    """Portfolio manager synthesizes meshed views into target trades."""

    name: str = "portfolio"
    checkpoint: bool = True

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
            bb.environment.per_symbol_context(),
            positions_ctx,
            account_ctx,
            max_new_positions=ctx.config.risk.max_orders_per_cycle,
        )
        bb.commentary = pm.get("portfolio_commentary", "")
        bb.environment.set_domain("portfolio", pm)
        ctx.journal.record(
            "portfolio.decision",
            {"proposals": pm.get("proposals", []), "commentary": bb.commentary},
        )
        bb.events.emit(
            "domain.write",
            "portfolio",
            {"proposals": len(pm.get("proposals", []))},
        )
        # Stash raw PM output for the materialize stage.
        bb.environment.global_context["_pm_raw"] = pm
        return True


@dataclass
class MaterializeStage(PipelineStage):
    """Convert PM dollar targets into share/contract proposals."""

    name: str = "materialize"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        raw = bb.environment.global_context.get("_pm_raw", {}).get("proposals", [])
        bb.proposals = _materialize_proposals(raw, bb)
        return True


@dataclass
class RiskStage(PipelineStage):
    """Deterministic guards + LLM veto."""

    name: str = "risk"
    checkpoint: bool = True

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
        bb.environment.set_domain(
            "risk",
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
def _analyze_one(ctx: CycleContext, cand: dict) -> None:
    bb = ctx.blackboard
    env = bb.environment
    symbol = cand.get("symbol", "").upper()
    snap = bb.snapshots.get(symbol) or ctx.market.snapshot(symbol)
    headlines = ctx.news_by_symbol.get(symbol, [])

    if ctx.config.parallel_workers > 1:
        with ThreadPoolExecutor(max_workers=2) as pool:
            tech_fut = pool.submit(ctx.agents.technical.analyze, snap)
            fund_fut = pool.submit(
                ctx.agents.fundamental.analyze, snap, headlines=headlines
            )
            tech = tech_fut.result()
            fund = fund_fut.result()
    else:
        tech = ctx.agents.technical.analyze(snap)
        fund = ctx.agents.fundamental.analyze(snap, headlines=headlines)

    bb.add_signal(tech)
    bb.add_signal(fund)
    env.set_domain(f"technical:{symbol}", {"symbol": symbol, "signal": tech.to_context()})
    env.set_domain(f"fundamental:{symbol}", {"symbol": symbol, "signal": fund.to_context()})
    bb.events.emit("domain.write", f"technical:{symbol}", {"direction": tech.direction.value})

    meshed = ctx.agents.meshing.mesh(
        symbol,
        [tech, fund],
        scanner_reason=cand.get("reason", ""),
        snapshot_context=snap.to_context() if snap else None,
    )
    env.set_meshed(meshed)
    bb.add_signal(meshed.to_signal())
    ctx.journal.record("meshing.view", meshed.to_context())
    bb.events.emit("domain.write", f"meshed:{symbol}", meshed.to_context())

    _maybe_options(ctx, symbol, snap, meshed)


def _maybe_options(
    ctx: CycleContext, symbol: str, snap: SymbolSnapshot, meshed
) -> None:
    bb = ctx.blackboard
    combined_dir = meshed.effective_direction
    combined_conv = meshed.effective_conviction
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
            bb.environment.set_domain(f"options:{symbol}", idea)


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
                    limit_price=marketable_limit(price, side),
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
                    limit_price=marketable_limit(price, side),
                )
            )
    return proposals
