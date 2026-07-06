"""Pipeline stages — composable steps extracted from the monolithic orchestrator."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace

from aoa.agents.base import Direction, Signal, TradeProposal, parse_side
from aoa.brokerage.base import BrokerError
from aoa.brokerage.models import AssetClass, OptionContract, Side
from aoa.data.market_data import PRIMARY_TIMEFRAME
from aoa.execution.pricing import marketable_limit
from aoa.plasticity.trust import notional_trust_multiplier
from aoa.swarm.context import CycleContext
from aoa.swarm.environment import MeshedView
from aoa.swarm.pipeline import PipelineStage
from aoa.swarm.trading_protocol import report_from_signal


@dataclass
class IntakeStage(PipelineStage):
    """Pull account state, resolve universe, build market snapshots."""

    name: str = "intake"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        ctx.market.clear_cache()
        ctx.news.clear_cache()

        raw_account = ctx.broker.get_account()
        bb.positions = ctx.broker.get_positions()
        try:
            bb.open_orders = ctx.broker.list_orders("open")
        except Exception:  # noqa: BLE001 — never let an order-list hiccup halt a cycle
            bb.open_orders = []

        ctx.update_starting_equity(raw_account.equity)
        unsettled = ctx.state.unsettled_cash()
        effective_settled = max(0.0, raw_account.settled_cash - unsettled)
        bb.account = replace(raw_account, settled_cash=effective_settled)
        ctx.journal.record(
            "cycle.start",
            {
                "mode": ctx.config.trading_mode,
                "equity": bb.account.equity,
                "settled_cash_raw": raw_account.settled_cash,
                "unsettled_cash": unsettled,
                "settled_cash_effective": effective_settled,
                "starting_equity": ctx.starting_equity,
                "n_positions": len(bb.positions),
            },
        )

        if ctx.config.universe:
            bb.universe = list(ctx.config.universe)
        else:
            try:
                bb.universe = ctx.broker.get_most_active(limit=25)
            except BrokerError as exc:
                msg = f"Failed to resolve trading universe: {exc}"
                ctx.notes.append(msg)
                ctx.journal.record(
                    "broker.error",
                    {"op": "resolve_universe", "error": str(exc)},
                )
                bb.universe = []
                return False

        if not bb.universe:
            ctx.notes.append("Empty universe — nothing to analyze.")
            return False

        bb.snapshots = ctx.market.snapshots(bb.universe)
        bb.environment.global_context = {
            "mode": ctx.config.trading_mode,
            "universe_size": len(bb.universe),
        }
        if ctx.plasticity and ctx.plasticity.enabled:
            ctx.plasticity.reload()
            bb.environment.global_context["plasticity"] = ctx.plasticity.memory.to_context()
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
            bb.candidates = _exit_review_candidates(bb)
        return True


@dataclass
class AnalyzeStage(PipelineStage):
    """Per-candidate technical + fundamental analysis, meshing, and options."""

    name: str = "analyze"
    checkpoint: bool = True

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        candidates = list(bb.candidates)
        if not candidates and bb.positions:
            for pos in bb.positions:
                if pos.qty <= 0 or pos.asset_class is AssetClass.OPTION:
                    continue
                candidates.append(
                    {
                        "symbol": pos.symbol.upper(),
                        "reason": "existing position — reviewing for exit",
                        "priority": 0.5,
                    }
                )

        symbols = [c.get("symbol", "").upper() for c in candidates if c.get("symbol")]
        if ctx.config.news_enabled and symbols:
            ctx.news_by_symbol = ctx.news.headlines(symbols, limit=ctx.config.news_limit)
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
        prior_pending = dict(ctx.adapt_pending)
        new_pending: dict[str, dict] = {}
        n_learned = 0
        n_adapted = 0

        if workers == 1 or len(candidates) <= 1:
            for cand in candidates:
                result = _compute_analysis(ctx, cand, prior_pending)
                _apply_analysis(ctx, result)
                n_learned += result.n_learned
                n_adapted += result.n_adapted
                new_pending.update(result.pending)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_compute_analysis, ctx, cand, prior_pending)
                    for cand in candidates
                ]
                results = [fut.result() for fut in as_completed(futures)]
            for result in sorted(results, key=lambda r: r.symbol):
                _apply_analysis(ctx, result)
                n_learned += result.n_learned
                n_adapted += result.n_adapted
                new_pending.update(result.pending)

        if ctx.signal_adapter is not None:
            ctx.adapt_pending.clear()
            ctx.adapt_pending.update(new_pending)
            ctx.journal.record(
                "adapt.applied",
                {
                    "signals_adapted": n_adapted,
                    "outcomes_learned": n_learned,
                    "total_updates": ctx.signal_adapter.updates,
                },
            )
        return True


@dataclass
class PortfolioStage(PipelineStage):
    """Portfolio manager synthesizes meshed views into target trades."""

    name: str = "portfolio"
    checkpoint: bool = True

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        account_ctx = bb.account.to_context()
        positions_ctx = [p.to_context() for p in bb.positions]
        pm = ctx.agents.portfolio.decide(
            bb.environment.per_symbol_context(),
            positions_ctx,
            account_ctx,
            max_new_positions=ctx.config.risk.max_orders_per_cycle,
            plasticity_context=ctx.plasticity.prompt_block() if ctx.plasticity else "",
            trading_agents_enabled=ctx.config.trading_agents_enabled,
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
        ctx.portfolio_output = pm
        return True


@dataclass
class MaterializeStage(PipelineStage):
    """Convert PM dollar targets into share/contract proposals."""

    name: str = "materialize"

    def run(self, ctx: CycleContext) -> bool:
        bb = ctx.blackboard
        raw = ctx.portfolio_output.get("proposals", [])
        symbol_trust: dict[str, float] = {}
        if ctx.plasticity is not None:
            symbol_trust = dict(ctx.plasticity.memory.symbol_trust)
        bb.proposals = _materialize_proposals(
            raw, bb, journal=ctx.journal, symbol_trust=symbol_trust
        )
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
            plasticity_context=ctx.plasticity.prompt_block() if ctx.plasticity else "",
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
class RiskDebateStage(PipelineStage):
    """TradingAgents risk-management debate (risk-seeking / neutral / conservative)."""

    name: str = "risk_debate"

    def should_run(self, ctx: CycleContext) -> bool:
        return ctx.config.trading_agents_enabled and bool(ctx.blackboard.proposals)

    def run(self, ctx: CycleContext) -> bool:
        if not ctx.config.trading_agents_enabled:
            return True
        bb = ctx.blackboard
        debate = ctx.agents.risk_debate.deliberate(
            bb.proposals, bb.account, bb.positions
        )
        ctx.agents.risk_debate.apply_vetoes(bb.proposals, debate)
        ctx.journal.record("risk.debate", debate.to_context())
        bb.environment.set_domain("risk_debate", debate.to_context())
        return True


@dataclass
class FundManagerStage(PipelineStage):
    """TradingAgents fund manager final approval before execution."""

    name: str = "fund_manager"

    def should_run(self, ctx: CycleContext) -> bool:
        return ctx.config.trading_agents_enabled and bool(ctx.blackboard.proposals)

    def run(self, ctx: CycleContext) -> bool:
        if not ctx.config.trading_agents_enabled:
            return True
        bb = ctx.blackboard
        risk_summary = ""
        risk_slice = bb.environment.domains.get("risk_debate")
        if risk_slice:
            risk_summary = str(risk_slice.effective().get("facilitator_summary", ""))
        decision = ctx.agents.fund_manager.review(
            bb.proposals,
            bb.account,
            risk_debate_summary=risk_summary,
            portfolio_commentary=bb.commentary,
        )
        ctx.agents.fund_manager.apply_decision(bb.proposals, decision)
        ctx.journal.record("fund_manager.review", decision)
        bb.environment.set_domain("fund_manager", decision)
        return True


@dataclass
class ExecuteStage(PipelineStage):
    """Submit approved trades (or simulate in dry-run)."""

    name: str = "execute"

    def should_run(self, ctx: CycleContext) -> bool:
        return any(p.approved for p in ctx.blackboard.proposals)

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


@dataclass
class PlasticityStage(PipelineStage):
    """Consolidate journal events into durable cross-cycle memory."""

    name: str = "plasticity"

    def should_run(self, ctx: CycleContext) -> bool:
        return ctx.plasticity is not None and ctx.plasticity.enabled

    def run(self, ctx: CycleContext) -> bool:
        if ctx.plasticity is None or not ctx.plasticity.enabled:
            return True
        delta = ctx.plasticity.consolidate()
        ctx.blackboard.environment.set_domain("plasticity", delta)
        return True


def default_stages() -> list[PipelineStage]:
    return [
        IntakeStage(),
        ScanStage(),
        AnalyzeStage(),
        PortfolioStage(),
        MaterializeStage(),
        RiskStage(),
        RiskDebateStage(),
        FundManagerStage(),
        ExecuteStage(),
        PlasticityStage(),
    ]


# ----------------------------------------------------------------- analysis
@dataclass
class SymbolAnalysisResult:
    symbol: str
    tech: Signal
    fund: Signal
    meshed: MeshedView
    n_learned: int = 0
    n_adapted: int = 0
    pending: dict[str, dict] = field(default_factory=dict)
    options_idea: dict | None = None
    option_contract: OptionContract | None = None
    options_error: tuple[str, str] | None = None
    news: Signal | None = None
    sentiment: Signal | None = None
    research_debate: dict | None = None
    analyst_reports: list[dict] | None = None


def _compute_analysis(
    ctx: CycleContext,
    cand: dict,
    prior_pending: dict[str, dict],
) -> SymbolAnalysisResult:
    """Analyze one candidate without mutating shared cycle state (thread-safe)."""
    bb = ctx.blackboard
    symbol = cand.get("symbol", "").upper()
    snap = bb.snapshots.get(symbol) or ctx.market.snapshot(symbol)
    headlines = ctx.news_by_symbol.get(symbol, [])
    pending: dict[str, dict] = {}
    n_learned = 0
    n_adapted = 0

    if ctx.config.trading_agents_enabled:
        workers = min(4, max(1, ctx.config.parallel_workers))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            tech_fut = pool.submit(ctx.agents.technical.analyze, snap)
            fund_fut = pool.submit(ctx.agents.fundamental.analyze, snap, headlines=None)
            news_fut = pool.submit(ctx.agents.news.analyze, snap, headlines=headlines)
            sent_fut = pool.submit(ctx.agents.sentiment.analyze, snap, headlines=headlines)
            tech = tech_fut.result()
            fund = fund_fut.result()
            news = news_fut.result()
            sentiment = sent_fut.result()

        price = snap.reference_price() if snap else None
        adapted, n_learned, n_adapted, pending_update = _adapt_analyst_signals(
            ctx.signal_adapter,
            prior_pending,
            symbol,
            [tech, fund, news, sentiment],
            price,
        )
        pending.update(pending_update)
        tech, fund, news, sentiment = adapted

        reports = [
            report_from_signal(tech, analyst="technical"),
            report_from_signal(fund, analyst="fundamental"),
            report_from_signal(news, analyst="news"),
            report_from_signal(sentiment, analyst="sentiment"),
        ]
        debate = ctx.agents.research.debate(
            symbol,
            reports,
            rounds=ctx.config.trading_agents_debate_rounds,
        )
        meshed = ctx.agents.meshing.mesh(
            symbol,
            [tech, fund, news, sentiment],
            scanner_reason=cand.get("reason", ""),
            snapshot_context=snap.to_context() if snap else None,
            research_context=debate.to_context(),
        )
        analyst_reports = [r.to_context() for r in reports]
        research_debate = debate.to_context()
    else:
        news = None
        sentiment = None
        analyst_reports = None
        research_debate = None

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

        price = snap.reference_price() if snap else None
        adapted, n_learned, n_adapted, pending_update = _adapt_analyst_signals(
            ctx.signal_adapter,
            prior_pending,
            symbol,
            [tech, fund],
            price,
        )
        pending.update(pending_update)
        tech, fund = adapted

        meshed = ctx.agents.meshing.mesh(
            symbol,
            [tech, fund],
            scanner_reason=cand.get("reason", ""),
            snapshot_context=snap.to_context() if snap else None,
        )

    options_idea = None
    option_contract = None
    combined_dir = meshed.effective_direction
    combined_conv = meshed.effective_conviction
    price = snap.reference_price() if snap else None
    if (
        combined_dir is not Direction.NEUTRAL
        and combined_conv >= 0.55
        and price
        and bb.account
        and bb.account.options_level >= 2
    ):
        try:
            idea = ctx.agents.options.propose(symbol, combined_dir, combined_conv, price)
        except BrokerError as exc:
            idea = None
            options_error = (symbol, str(exc))
        else:
            options_error = None
        if idea:
            option_contract = idea.pop("_contract", None)
            options_idea = idea
    else:
        options_error = None

    return SymbolAnalysisResult(
        symbol=symbol,
        tech=tech,
        fund=fund,
        meshed=meshed,
        n_learned=n_learned,
        n_adapted=n_adapted,
        pending=pending,
        options_idea=options_idea,
        option_contract=option_contract,
        options_error=options_error,
        news=news,
        sentiment=sentiment,
        research_debate=research_debate,
        analyst_reports=analyst_reports,
    )


def _apply_analysis(ctx: CycleContext, result: SymbolAnalysisResult) -> None:
    """Merge one candidate's analysis into the shared blackboard (main thread)."""
    bb = ctx.blackboard
    env = bb.environment
    symbol = result.symbol
    options_error = result.options_error
    if options_error is not None:
        sym, err = options_error
        msg = f"Option chain unavailable for {sym}: {err}"
        ctx.notes.append(msg)
        ctx.journal.record(
            "broker.error",
            {"op": "get_option_chain", "symbol": sym, "error": err},
        )

    if result.analyst_reports is not None:
        signals = [result.tech, result.fund, result.news, result.sentiment]
        for sig in signals:
            if sig is not None:
                bb.add_signal(sig)
        env.set_domain(
            f"analyst_reports:{symbol}",
            {"symbol": symbol, "reports": result.analyst_reports},
        )
        for sig in signals:
            if sig is None:
                continue
            env.set_domain(
                f"{sig.source}:{symbol}",
                {"symbol": symbol, "signal": sig.to_context()},
            )
            ctx.journal.record(
                "analyst.report",
                {"symbol": symbol, "analyst": sig.source, "signal": sig.to_context()},
            )
        if result.research_debate is not None:
            env.set_domain(f"research:{symbol}", result.research_debate)
            ctx.journal.record("research.debate", result.research_debate)
    else:
        bb.add_signal(result.tech)
        bb.add_signal(result.fund)
        env.set_domain(
            f"technical:{symbol}",
            {"symbol": symbol, "signal": result.tech.to_context()},
        )
        env.set_domain(
            f"fundamental:{symbol}",
            {"symbol": symbol, "signal": result.fund.to_context()},
        )
        bb.events.emit(
            "domain.write", f"technical:{symbol}", {"direction": result.tech.direction.value}
        )

    env.set_meshed(result.meshed)
    bb.add_signal(result.meshed.to_signal())
    ctx.journal.record("meshing.view", result.meshed.to_context())
    bb.events.emit("domain.write", f"meshed:{symbol}", result.meshed.to_context())

    if result.options_idea is not None:
        if result.option_contract is not None:
            bb.option_contracts[result.option_contract.symbol] = result.option_contract
        bb.options_ideas[symbol] = result.options_idea
        env.set_domain(f"options:{symbol}", result.options_idea)


def _exit_review_candidates(bb) -> list[dict]:
    """When the scanner finds nothing, still give agents context on open positions."""
    candidates: list[dict] = []
    for pos in bb.positions:
        if pos.qty <= 0:
            continue
        symbol = pos.symbol.upper()
        if pos.asset_class is AssetClass.OPTION:
            candidates.append(
                {
                    "symbol": symbol,
                    "priority": 0.0,
                    "reason": "existing position — reviewing for exit",
                }
            )
            continue
        candidates.append(
            {
                "symbol": symbol,
                "priority": 0.0,
                "reason": "existing position — reviewing for exit",
            }
        )
    return candidates


def _materialize_proposals(
    raw: list[dict],
    bb,
    *,
    journal=None,
    symbol_trust: dict[str, float] | None = None,
) -> list[TradeProposal]:
    proposals: list[TradeProposal] = []
    trust_map = symbol_trust or {}
    pos_by_symbol = {p.symbol: p for p in bb.positions}
    held_or_pending = {p.symbol for p in bb.positions if p.qty != 0}
    held_or_pending |= {o.symbol for o in bb.open_orders}

    for item in raw:
        symbol = item.get("symbol", "").upper()
        instrument = item.get("instrument", "equity")
        side = parse_side(item.get("side", "buy"))
        if side is None:
            continue
        target = float(item.get("target_notional", 0) or 0)
        if target > 0:
            target *= notional_trust_multiplier(trust_map.get(symbol, 0.0))
        if target <= 0 and side is Side.BUY:
            continue

        if side is Side.BUY and symbol in held_or_pending:
            if journal is not None:
                journal.record(
                    "proposal.skipped",
                    {"symbol": symbol, "reason": "existing position or pending order"},
                )
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
            price = snap.reference_price() if snap else None
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
            stop_price, take_profit = (None, None)
            if side is Side.BUY:
                stop_price, take_profit = _protective_levels(symbol, price, bb)
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
                    stop_price=stop_price,
                    take_profit_price=take_profit,
                )
            )
    return proposals


def _protective_levels(
    symbol: str, price: float, bb
) -> tuple[float, float]:
    """Derive a protective stop and take-profit for a new long."""
    tech = next(
        (s for s in bb.signals_for(symbol) if s.source == "technical"), None
    )
    levels = tech.key_levels if tech else {}
    snap = bb.snapshots.get(symbol)
    daily = snap.technicals.get(PRIMARY_TIMEFRAME, {}) if snap and snap.technicals else {}
    atr = daily.get("atr_14") or 0.0

    stop = levels.get("stop")
    if not (isinstance(stop, (int, float)) and 0 < stop < price):
        stop = (price - 1.5 * atr) if atr > 0 else price * 0.92
    if stop >= price:
        stop = price * 0.92

    resistance = levels.get("resistance")
    if isinstance(resistance, (int, float)) and resistance > price:
        take_profit = float(resistance)
    else:
        take_profit = price + 2 * (price - stop)

    return round(float(stop), 2), round(float(take_profit), 2)


def _pending_entry(signal: Signal) -> dict:
    """Minimal record of a raw signal needed to score it next cycle."""
    return {
        "agent": signal.source,
        "direction": signal.direction.value,
        "conviction": signal.conviction,
        "horizon": signal.horizon,
    }


def _adapt_analyst_signals(
    adapter,
    prior_pending: dict[str, dict],
    symbol: str,
    signals: list[Signal],
    price: float | None,
) -> tuple[list[Signal], int, int, dict[str, dict]]:
    """Learn from the prior cycle, adapt convictions, and queue pending for the next."""
    if adapter is None:
        return signals, 0, 0, {}

    n_learned = _learn_from_prior(adapter, prior_pending, symbol, price)
    pending: dict[str, dict] = {}
    if price:
        pending[symbol] = {
            "price": price,
            "signals": [_pending_entry(s) for s in signals],
        }
    adapted = [adapter.adapt_signal(s) for s in signals]
    n_adapted = sum("adapted" in s.tags for s in adapted)
    return adapted, n_learned, n_adapted, pending


def _learn_from_prior(
    adapter,
    prior_pending: dict[str, dict],
    symbol: str,
    price: float | None,
) -> int:
    """Score the previous cycle's signals against the realized move."""
    prior = prior_pending.get(symbol)
    if not prior or not price or not prior.get("price"):
        return 0
    realized = (price - prior["price"]) / prior["price"]
    learned = 0
    for s in prior["signals"]:
        adapter.record_outcome(
            agent=s["agent"],
            direction=s["direction"],
            conviction=s["conviction"],
            realized_return=realized,
            horizon=s["horizon"],
        )
        learned += 1
    return learned
