"""Notification policy — decide what to push vs journal-only."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aoa.notify.types import NotificationKind, StructuredNotification

if TYPE_CHECKING:
    from aoa.analytics.store import AnalyticsStore
    from aoa.team.orchestrator import TeamCycleResult


class NotificationPolicy:
    """Push on opportunities, halts, and high-conviction approved proposals."""

    def __init__(
        self,
        *,
        push_opportunities: bool = True,
        push_halts: bool = True,
        min_conviction: float = 0.65,
        push_routine_cycles: bool = False,
    ) -> None:
        self.push_opportunities = push_opportunities
        self.push_halts = push_halts
        self.min_conviction = min_conviction
        self.push_routine_cycles = push_routine_cycles

    def evaluate_cycle(
        self,
        result: TeamCycleResult,
        *,
        run_id: str = "",
    ) -> list[StructuredNotification]:
        out: list[StructuredNotification] = []

        if result.halted and self.push_halts:
            out.append(
                StructuredNotification(
                    kind=NotificationKind.ALERT,
                    title="Swarm halted",
                    message=result.halt_reason or "Cycle halted by health gate.",
                    run_id=run_id,
                    journal_event="team.halt",
                    priority="high",
                )
            )

        if result.cycle:
            for proposal in result.cycle.blackboard.proposals:
                if not proposal.approved:
                    continue
                ctx = proposal.to_context()
                conviction = _proposal_conviction(ctx, result)
                if conviction is not None and conviction < self.min_conviction:
                    continue
                vol_ratio = _volume_ratio(ctx.get("symbol", ""), result)
                out.append(
                    StructuredNotification(
                        kind=NotificationKind.OPPORTUNITY,
                        title=_opp_title(ctx),
                        message=_proposal_message(ctx, result),
                        symbol=ctx.get("symbol", ""),
                        conviction=conviction,
                        volume_ratio=vol_ratio,
                        notional=ctx.get("est_notional"),
                        metrics={
                            "side": ctx.get("side"),
                            "strategy": ctx.get("strategy"),
                            "qty": ctx.get("qty"),
                        },
                        run_id=run_id,
                        journal_event="swarm.proposal.approved",
                        priority="high" if conviction and conviction >= 0.8 else "normal",
                    )
                )

        for trend in result.trends:
            ctx = trend.to_context()
            conf = ctx.get("strength")
            if conf is None or conf < self.min_conviction:
                continue
            if not self.push_opportunities:
                continue
            sym = ctx.get("symbol", "")
            out.append(
                StructuredNotification(
                    kind=NotificationKind.ANALYSIS,
                    title=f"{sym} trend · {ctx.get('direction', '—')}",
                    message=ctx.get("rationale", "")[:280],
                    symbol=sym,
                    conviction=conf,
                    volume_ratio=_volume_ratio(sym, result),
                    metrics={"timeframe": ctx.get("timeframe"), "agent": "Tom"},
                    run_id=run_id,
                    journal_event="team.tom.trends",
                )
            )

        if self.push_routine_cycles and not out and not result.halted:
            out.append(
                StructuredNotification(
                    kind=NotificationKind.ANALYSIS,
                    title="Cycle complete",
                    message=result.ceo.summary if result.ceo else "Routine cycle finished.",
                    run_id=run_id,
                    journal_event="team.cycle.complete",
                )
            )

        return _dedupe(out)

    def log_all(
        self,
        store: AnalyticsStore,
        notifications: list[StructuredNotification],
        *,
        pushed_ids: set[int] | None = None,
    ) -> None:
        pushed = pushed_ids or set()
        for i, note in enumerate(notifications):
            store.log_notification(
                kind=note.kind.value,
                title=note.title,
                message=note.message,
                payload=note.to_payload(),
                run_id=note.run_id,
                pushed=i in pushed,
            )


def _dedupe(notifications: list[StructuredNotification]) -> list[StructuredNotification]:
    seen: set[tuple[str, str, str]] = set()
    out: list[StructuredNotification] = []
    for n in notifications:
        key = (n.kind.value, n.symbol, n.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def _proposal_conviction(ctx: dict, result: TeamCycleResult) -> float | None:
    sym = (ctx.get("symbol") or "").upper()
    if result.decision:
        for rec in result.decision.recommendations:
            if (rec.get("symbol") or "").upper() == sym:
                return rec.get("confidence")
    return None


def _volume_ratio(symbol: str, result: TeamCycleResult) -> float | None:
    if not result.cycle or not symbol:
        return None
    snap = result.cycle.blackboard.snapshots.get(symbol.upper())
    if snap is None:
        return None
    metrics = getattr(snap, "volume_metrics", None)
    if isinstance(metrics, dict):
        return metrics.get("volume_ratio")
    if hasattr(snap, "indicators"):
        ind = snap.indicators or {}
        vm = ind.get("volume_metrics") if isinstance(ind, dict) else None
        if isinstance(vm, dict):
            return vm.get("volume_ratio")
    return None


def _opp_title(ctx: dict) -> str:
    sym = ctx.get("symbol", "")
    side = ctx.get("side", "")
    return f"{sym} · {side} opportunity"


def _proposal_message(ctx: dict, result: TeamCycleResult) -> str:
    parts = [
        f"{ctx.get('side', '').upper()} {ctx.get('qty', '')} {ctx.get('symbol', '')}",
        ctx.get("strategy", ""),
    ]
    if ctx.get("est_notional"):
        parts.append(f"~${ctx['est_notional']:,.0f}")
    if result.decision and result.decision.summary:
        parts.append(result.decision.summary[:120])
    return " · ".join(p for p in parts if p)
