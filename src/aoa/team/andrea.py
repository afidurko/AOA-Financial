"""Andrea — risk management, hedging, and pre-execution trade plans."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

from aoa.agents.base import Agent, TradeProposal
from aoa.brokerage.models import AssetClass, Side
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import (
    AlgorithmReport,
    CatalystReport,
    DecisionBrief,
    MarketContextReport,
    RiskPlanReport,
    TradePlanLevels,
    TrendReport,
)

if TYPE_CHECKING:
    from aoa.brokerage.base import Broker
    from aoa.config import Config

_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "approved_for_execution": {"type": "boolean"},
        "hedging": {"type": "string"},
        "options_analysis": {"type": "string"},
        "hedge_recommendation": {"type": "string"},
        "pre_execution_note": {"type": "string"},
        "action": {"type": "string"},
        "instrument": {"type": "string", "enum": ["equity", "option", "hedge", "watch"]},
        "entry_price": {"type": "number"},
        "stop_loss": {"type": "number"},
        "take_profit": {"type": "number"},
        "quantity": {"type": "number"},
    },
    "required": [
        "summary",
        "approved_for_execution",
        "hedging",
        "options_analysis",
        "hedge_recommendation",
        "pre_execution_note",
        "action",
        "instrument",
        "entry_price",
        "stop_loss",
        "take_profit",
        "quantity",
    ],
    "additionalProperties": False,
}


class AndreaAgent(Agent):
    name = "andrea"
    display_name = "Andrea"
    role = "Risk Manager & Pre-Execution Analyst"

    system_prompt = (
        "You are Andrea, the risk manager on an autonomous CASH-account trading team. "
        "Before any order executes, you produce pre-execution plans with entry, stop-loss, "
        "take-profit, quantity, hedging ideas, and options-structure notes. You may recommend "
        "protective puts, collars, or cash-secured hedges when event risk is elevated. "
        "Reject or downgrade trades when reward/risk is poor, catalyst risk is high, or "
        "position size exceeds prudent limits. Quantities must respect max position sizing. "
        "Never propose naked short options or margin strategies."
    )

    def __init__(self, llm, broker: Broker, config: Config) -> None:
        super().__init__(llm)
        self.broker = broker
        self.config = config

    def analyze_plans(
        self,
        *,
        proposals: list[TradeProposal],
        decision: DecisionBrief | None,
        trends: list[TrendReport],
        algorithms: list[AlgorithmReport],
        market_contexts: list[MarketContextReport],
        catalysts: list[CatalystReport],
        snapshots: dict[str, SymbolSnapshot],
        options_ideas: dict[str, dict] | None = None,
    ) -> list[RiskPlanReport]:
        account = self.broker.get_account()
        targets = _target_symbols(proposals, decision)
        if not targets:
            return []

        trend_by = {t.symbol: t for t in trends}
        algo_by = {a.symbol: a for a in algorithms}
        morgan_by = {m.symbol: m for m in market_contexts}
        catalyst_by = {c.symbol: c for c in catalysts}
        options_ideas = options_ideas or {}

        reports: list[RiskPlanReport] = []
        prop_by = {p.symbol.upper(): p for p in proposals}
        for sym in sorted(targets):
            prop = prop_by.get(sym)
            snap = snapshots.get(sym)
            ctx = _build_symbol_context(
                sym,
                prop=prop,
                trend=trend_by.get(sym),
                algo=algo_by.get(sym),
                market=morgan_by.get(sym),
                catalyst=catalyst_by.get(sym),
                options_idea=options_ideas.get(sym),
                account=account.to_context(),
                max_position_pct=self.config.risk.max_position_pct,
            )
            try:
                r = self.llm.structured(
                    self.system_prompt,
                    ctx + "\n\nProduce the pre-execution risk plan as JSON.",
                    _SCHEMA,
                )
                report = _report_from_llm(sym, r, account.equity, self.config.risk.max_position_pct)
            except Exception:  # noqa: BLE001
                report = _fallback_plan(
                    sym, prop, snap, account.equity, self.config.risk.max_position_pct
                )
            if prop and not prop.approved:
                report = RiskPlanReport(
                    symbol=sym,
                    summary=f"{sym}: swarm risk veto — {report.summary}",
                    approved_for_execution=False,
                    plan=report.plan,
                    hedging=report.hedging,
                    stats=report.stats,
                )
            reports.append(report)
        return reports


def _target_symbols(
    proposals: list[TradeProposal], decision: DecisionBrief | None
) -> set[str]:
    symbols = {p.symbol.upper() for p in proposals if p.symbol}
    if decision:
        for rec in decision.recommendations:
            sym = str(rec.get("symbol", "")).upper()
            action = str(rec.get("action", ""))
            if sym and action in {"consider_long", "consider_short_exit", "watch"}:
                symbols.add(sym)
    return symbols


def _build_symbol_context(
    symbol: str,
    *,
    prop: TradeProposal | None,
    trend: TrendReport | None,
    algo: AlgorithmReport | None,
    market: MarketContextReport | None,
    catalyst: CatalystReport | None,
    options_idea: dict | None,
    account: dict,
    max_position_pct: float,
) -> str:
    chunks = [
        f"Symbol: {symbol}",
        f"Account: {json.dumps(account, default=str)}",
        f"Max position pct: {max_position_pct}",
    ]
    if prop:
        chunks.append(f"Swarm proposal: {json.dumps(prop.to_context(), default=str)}")
    if trend:
        chunks.append(f"Tom trend: {json.dumps(trend.to_context(), default=str)}")
    if algo:
        chunks.append(f"Julie algorithm: {json.dumps(algo.to_context(), default=str)}")
    if market:
        chunks.append(f"Morgan context: {json.dumps(market.to_context(), default=str)}")
    if catalyst:
        chunks.append(f"Hailey catalyst: {json.dumps(catalyst.to_context(), default=str)}")
    if options_idea:
        chunks.append(f"Options idea: {json.dumps(options_idea, default=str)}")
    return "\n".join(chunks)


def _report_from_llm(
    symbol: str,
    r: dict[str, Any],
    equity: float,
    max_position_pct: float,
) -> RiskPlanReport:
    entry = _f(r.get("entry_price"))
    stop = _f(r.get("stop_loss"))
    tp = _f(r.get("take_profit"))
    qty = _f(r.get("quantity")) or 1.0
    qty = _clamp_qty(qty, entry, equity, max_position_pct)
    est_cost, max_risk, rr = _plan_math(entry, stop, tp, qty)
    plan = TradePlanLevels(
        symbol=symbol,
        action=str(r.get("action", "watch")),
        instrument=str(r.get("instrument", "equity")),
        entry_price=entry,
        stop_loss=stop,
        take_profit=tp,
        quantity=qty,
        est_cost=est_cost,
        max_risk_dollars=max_risk,
        reward_risk_ratio=rr,
        hedge_recommendation=str(r.get("hedge_recommendation", "")),
        options_analysis=str(r.get("options_analysis", "")),
        pre_execution_note=str(r.get("pre_execution_note", "")),
    )
    stats = _viz_stats(entry, stop, tp, qty, est_cost, max_risk, rr, equity, max_position_pct)
    return RiskPlanReport(
        symbol=symbol,
        summary=str(r.get("summary", "")),
        approved_for_execution=bool(r.get("approved_for_execution")),
        plan=plan,
        hedging=str(r.get("hedging", "")),
        stats=stats,
    )


def _fallback_plan(
    symbol: str,
    prop: TradeProposal | None,
    snap: SymbolSnapshot | None,
    equity: float,
    max_position_pct: float,
) -> RiskPlanReport:
    price = prop.est_price if prop else (snap.reference_price() if snap else None)
    entry = float(price) if price else None
    stop = round(entry * 0.92, 2) if entry else None
    tp = round(entry * 1.08, 2) if entry else None
    qty = float(prop.qty) if prop else _clamp_qty(1.0, entry, equity, max_position_pct)
    est_cost, max_risk, rr = _plan_math(entry, stop, tp, qty)
    plan = TradePlanLevels(
        symbol=symbol,
        action="enter_long" if prop and prop.side is Side.BUY else "watch",
        instrument="option" if prop and prop.asset_class is AssetClass.OPTION else "equity",
        entry_price=entry,
        stop_loss=stop,
        take_profit=tp,
        quantity=qty,
        est_cost=est_cost,
        max_risk_dollars=max_risk,
        reward_risk_ratio=rr,
        pre_execution_note="Template plan — LLM unavailable.",
    )
    return RiskPlanReport(
        symbol=symbol,
        summary=f"{symbol}: deterministic risk template.",
        approved_for_execution=bool(prop.approved) if prop else False,
        plan=plan,
        hedging="No hedge suggested in template mode.",
        stats=_viz_stats(entry, stop, tp, qty, est_cost, max_risk, rr, equity, max_position_pct),
    )


def _plan_math(
    entry: float | None,
    stop: float | None,
    tp: float | None,
    qty: float,
) -> tuple[float, float, float | None]:
    if not entry or entry <= 0:
        return 0.0, 0.0, None
    est_cost = entry * qty
    if stop and stop < entry:
        max_risk = (entry - stop) * qty
        reward = (tp - entry) * qty if tp and tp > entry else 0.0
        rr = round(reward / max_risk, 2) if max_risk > 0 else None
    else:
        max_risk = est_cost * 0.08
        rr = None
    return round(est_cost, 2), round(max_risk, 2), rr


def _clamp_qty(qty: float, entry: float | None, equity: float, max_position_pct: float) -> float:
    if not entry or entry <= 0 or equity <= 0:
        return max(1.0, qty)
    cap = math.floor((equity * max_position_pct) / entry)
    cap = max(1.0, cap)
    return min(max(1.0, qty), cap)


def _viz_stats(
    entry: float | None,
    stop: float | None,
    tp: float | None,
    qty: float,
    est_cost: float,
    max_risk: float,
    rr: float | None,
    equity: float,
    max_position_pct: float,
) -> dict[str, Any]:
    prices = [p for p in (entry, stop, tp) if p is not None and p > 0]
    if not prices:
        return {
            "quantity": qty,
            "est_cost": est_cost,
            "max_risk_dollars": max_risk,
            "reward_risk_ratio": rr,
            "position_pct": 0.0,
            "risk_pct_equity": 0.0,
        }
    bar_low = min(prices) * 0.97
    bar_high = max(prices) * 1.03
    position_pct = (est_cost / equity * 100) if equity > 0 else 0.0
    risk_pct = (max_risk / equity * 100) if equity > 0 else 0.0
    return {
        "entry": entry,
        "stop_loss": stop,
        "take_profit": tp,
        "quantity": qty,
        "est_cost": est_cost,
        "max_risk_dollars": max_risk,
        "reward_risk_ratio": rr,
        "position_pct": round(position_pct, 2),
        "risk_pct_equity": round(risk_pct, 2),
        "max_position_pct": round(max_position_pct * 100, 1),
        "bar_low": round(bar_low, 2),
        "bar_high": round(bar_high, 2),
    }


def _f(value: Any) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None
