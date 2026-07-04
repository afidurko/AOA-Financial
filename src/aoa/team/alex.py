"""Alex — executive assistant: prioritize must-dos vs needs for the user."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from aoa.agents.base import Agent
from aoa.team.models import (
    AssistantBrief,
    PriorityItem,
    PriorityLevel,
)

if TYPE_CHECKING:
    from aoa.analytics.store import AnalyticsStore
    from aoa.team.orchestrator import TeamCycleResult

_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "focus": {"type": "string"},
        "must_do": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "action_hint": {"type": "string"},
                },
                "required": ["title", "detail"],
                "additionalProperties": False,
            },
        },
        "should_do": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "action_hint": {"type": "string"},
                },
                "required": ["title", "detail"],
                "additionalProperties": False,
            },
        },
        "can_wait": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["title", "detail"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "focus", "must_do", "should_do", "can_wait"],
    "additionalProperties": False,
}


class AlexAgent(Agent):
    name = "alex"
    display_name = "Alex"
    role = "Executive Assistant"

    system_prompt = (
        "You are Alex, the user's executive assistant for AOA Financial. You do NOT "
        "trade or change system settings. Your job is to triage everything competing "
        "for the user's attention into three buckets: MUST DO (blocking, urgent, or "
        "requires verification today), SHOULD DO ( valuable but not blocking), and "
        "CAN WAIT (informational or deferrable). Be concise, actionable, and honest "
        "about trade-offs. Never invent pending items not present in the context."
    )

    def prioritize(
        self,
        *,
        cycle: TeamCycleResult | None = None,
        analytics_store: AnalyticsStore | None = None,
        market_open: bool = True,
    ) -> AssistantBrief:
        ctx = _gather_context(
            cycle=cycle,
            analytics_store=analytics_store,
            market_open=market_open,
        )
        baseline = _deterministic_brief(ctx)
        try:
            prompt = (
                "User operations context (JSON):\n"
                f"{json.dumps(ctx, default=str)}\n\n"
                "Refine the deterministic triage below. Keep items grounded in context; "
                "you may merge duplicates and improve wording.\n"
                f"{json.dumps(baseline.to_context(), default=str)}"
            )
            r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
            return _merge_llm_brief(baseline, r)
        except Exception:  # noqa: BLE001 — fall back to rules engine
            return baseline


def _gather_context(
    *,
    cycle: TeamCycleResult | None,
    analytics_store: AnalyticsStore | None,
    market_open: bool,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {"market_open": market_open}
    if cycle:
        ctx.update(
            {
                "halted": cycle.halted,
                "halt_reason": cycle.halt_reason,
                "health": cycle.health.to_context() if cycle.health else None,
                "ceo": cycle.ceo.to_context() if cycle.ceo else None,
                "decision_summary": cycle.decision.summary if cycle.decision else "",
                "approved_proposals": _approved_proposals(cycle),
                "trend_count": len(cycle.trends),
                "market_context_count": len(cycle.market_contexts),
            }
        )
    if analytics_store is not None:
        ctx["pending_approvals"] = analytics_store.list_approvals(status="pending", limit=20)
        ctx["pending_research"] = analytics_store.list_research_proposals(
            status="pending", limit=20
        )
        ctx["roi"] = analytics_store.roi_summary(limit=10)
    return ctx


def _approved_proposals(cycle: TeamCycleResult) -> list[dict]:
    if not cycle.cycle:
        return []
    return [p.to_context() for p in cycle.cycle.blackboard.proposals if p.approved]


def _deterministic_brief(ctx: dict[str, Any]) -> AssistantBrief:
    must: list[PriorityItem] = []
    should: list[PriorityItem] = []
    later: list[PriorityItem] = []

    if ctx.get("halted"):
        must.append(
            PriorityItem(
                level=PriorityLevel.MUST,
                title="Swarm halted",
                detail=ctx.get("halt_reason") or "Cycle stopped by health gate.",
                source="team",
                action_hint="Review Bob health checks and fix blockers before next cycle.",
            )
        )

    health = ctx.get("health") or {}
    if health and not health.get("can_proceed", True):
        must.append(
            PriorityItem(
                level=PriorityLevel.MUST,
                title="Systems health critical",
                detail=health.get("summary", "Health gate failed."),
                source="bob",
                action_hint="Run `aoa team health` and resolve configuration or broker issues.",
            )
        )

    ceo = ctx.get("ceo") or {}
    for note in ceo.get("user_notifications") or []:
        level = PriorityLevel.MUST if _needs_user_action(note) else PriorityLevel.SHOULD
        bucket = must if level is PriorityLevel.MUST else should
        bucket.append(
            PriorityItem(
                level=level,
                title="CEO escalation",
                detail=note,
                source="aaron",
                action_hint="Open dashboard Approvals or update .env as indicated.",
            )
        )

    for item in ctx.get("pending_approvals") or []:
        must.append(
            PriorityItem(
                level=PriorityLevel.MUST,
                title=item.get("title", "Pending approval"),
                detail=item.get("summary", ""),
                source="approval_inbox",
                action_hint="Dashboard → Approvals tab → approve or reject.",
            )
        )

    for paper in ctx.get("pending_research") or []:
        score = paper.get("backtest_score") or 0
        level = PriorityLevel.SHOULD if score >= 0.5 else PriorityLevel.LATER
        bucket = should if level is PriorityLevel.SHOULD else later
        bucket.append(
            PriorityItem(
                level=level,
                title=f"Research: {paper.get('technique', 'edge')}",
                detail=paper.get("title", paper.get("abstract", ""))[:200],
                source="scholar",
                action_hint="Dashboard → Research tab → review paper and decide.",
            )
        )

    for prop in ctx.get("approved_proposals") or []:
        should.append(
            PriorityItem(
                level=PriorityLevel.SHOULD,
                title=f"Approved trade: {prop.get('symbol')} {prop.get('side')}",
                detail=f"Strategy {prop.get('strategy', '—')} · ~${prop.get('est_notional', 0):,.0f}",
                source="swarm",
                action_hint="Confirm execution in journal; verify dry-run vs paper mode.",
            )
        )

    if not must and not should:
        if ctx.get("market_open"):
            later.append(
                PriorityItem(
                    level=PriorityLevel.LATER,
                    title="Routine monitoring",
                    detail=ctx.get("decision_summary") or "No blockers; swarm operating normally.",
                    source="team",
                )
            )
        else:
            later.append(
                PriorityItem(
                    level=PriorityLevel.LATER,
                    title="Market closed",
                    detail="Review research proposals or run burn-in when ready.",
                    source="schedule",
                )
            )

    focus = must[0].title if must else (should[0].title if should else "No urgent items")
    summary = (
        f"{len(must)} must-do, {len(should)} should-do, {len(later)} can-wait."
        if (must or should)
        else "All clear — nothing blocking you right now."
    )
    return AssistantBrief(
        must_do=must,
        should_do=should,
        can_wait=later,
        summary=summary,
        focus=focus,
    )


def _needs_user_action(note: str) -> bool:
    lower = note.lower()
    return any(
        k in lower
        for k in ("verification", "confirm", "credential", "api_key", ".env", "needs your")
    )


def _merge_llm_brief(baseline: AssistantBrief, r: dict) -> AssistantBrief:
    def _items(raw: list[dict], level: PriorityLevel) -> list[PriorityItem]:
        out: list[PriorityItem] = []
        for row in raw:
            out.append(
                PriorityItem(
                    level=level,
                    title=str(row.get("title", "")),
                    detail=str(row.get("detail", "")),
                    action_hint=str(row.get("action_hint", "")),
                    source="alex",
                )
            )
        return out

    must = _items(r.get("must_do") or [], PriorityLevel.MUST) or baseline.must_do
    should = _items(r.get("should_do") or [], PriorityLevel.SHOULD) or baseline.should_do
    later = _items(r.get("can_wait") or [], PriorityLevel.LATER) or baseline.can_wait
    return AssistantBrief(
        must_do=must,
        should_do=should,
        can_wait=later,
        summary=str(r.get("summary") or baseline.summary),
        focus=str(r.get("focus") or baseline.focus),
    )
