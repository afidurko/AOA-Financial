"""Persist team cycle results into the analytics SQLite store."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from aoa.analytics.store import AnalyticsStore

if TYPE_CHECKING:
    from aoa.config import Config
    from aoa.team.orchestrator import TeamCycleResult


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]


class CycleAnalyticsBridge:
    """Sync live swarm cycles into queryable analytics storage."""

    def __init__(self, store: AnalyticsStore, config: Config) -> None:
        self.store = store
        self.config = config
        self._current_run_id = ""
        self._started_at = ""

    @classmethod
    def from_config(cls, config: Config) -> CycleAnalyticsBridge:
        return cls(AnalyticsStore(config.analytics_db_path), config)

    def begin_cycle(self) -> str:
        self._current_run_id = new_run_id()
        self._started_at = datetime.now(timezone.utc).isoformat()
        return self._current_run_id

    @property
    def run_id(self) -> str:
        return self._current_run_id

    def persist_cycle(self, result: TeamCycleResult) -> str:
        run_id = self._current_run_id or new_run_id()
        started = self._started_at or datetime.now(timezone.utc).isoformat()
        completed = datetime.now(timezone.utc).isoformat()

        payload = _cycle_payload(result)
        self.store.record_cycle(
            run_id=run_id,
            started_at=started,
            completed_at=completed,
            mode=self.config.trading_mode,
            halted=result.halted,
            halt_reason=result.halt_reason,
            payload=payload,
        )

        signals = _extract_signals(result)
        if signals:
            self.store.insert_signals(run_id, signals)

        proposals = _extract_proposals(result)
        if proposals:
            self.store.insert_proposals(run_id, proposals)

        return run_id

    def record_stage(self, stage: str, duration_ms: float, *, skipped: bool = False) -> None:
        if not self._current_run_id:
            return
        self.store.insert_stage_metric(
            self._current_run_id, stage, duration_ms, skipped=skipped
        )


def _cycle_payload(result: TeamCycleResult) -> dict[str, Any]:
    out: dict[str, Any] = {
        "halted": result.halted,
        "halt_reason": result.halt_reason,
    }
    if result.health:
        out["health"] = result.health.to_context()
    if result.decision:
        out["decision"] = result.decision.to_context()
    if result.ceo:
        out["ceo"] = result.ceo.to_context()
    if result.trends:
        out["trends"] = [t.to_context() for t in result.trends]
    if result.algorithms:
        out["algorithms"] = [a.to_context() for a in result.algorithms]
    if result.cycle:
        bb = result.cycle.blackboard
        out["commentary"] = bb.commentary
        out["candidates"] = bb.candidates
        if result.cycle.execution:
            out["execution"] = {
                "dry_run": result.cycle.execution.dry_run,
                "submitted": len(result.cycle.execution.submitted),
                "skipped": len(result.cycle.execution.skipped),
            }
        out["analyst_reports"] = _analyst_reports_from_env(bb.environment)
    return out


def _analyst_reports_from_env(environment) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for key in environment.domains:
        if not str(key).startswith("analyst_reports:"):
            continue
        domain = environment.domains[key].effective()
        reports.extend(domain.get("reports") or [])
    return reports


def _extract_signals(result: TeamCycleResult) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for trend in result.trends:
        ctx = trend.to_context()
        signals.append(
            {
                "ticker": ctx.get("symbol", ""),
                "agent": "Tom",
                "direction": ctx.get("direction", ""),
                "conviction": ctx.get("strength"),
                "summary": ctx.get("rationale", ""),
                "metrics": {"timeframe": ctx.get("timeframe")},
            }
        )
    for algo in result.algorithms:
        ctx = algo.to_context()
        signals.append(
            {
                "ticker": ctx.get("symbol", ""),
                "agent": "Julie",
                "direction": "validated" if ctx.get("validated") else "review",
                "conviction": ctx.get("adjusted_strength"),
                "summary": ctx.get("method_notes", ""),
                "metrics": {"signals": ctx.get("signals")},
            }
        )
    for mc in result.market_contexts:
        ctx = mc.to_context()
        signals.append(
            {
                "ticker": ctx.get("symbol", ""),
                "agent": "Morgan",
                "direction": ctx.get("volume_regime", ""),
                "conviction": ctx.get("volume_ratio"),
                "summary": ctx.get("summary", ""),
                "metrics": {"liquidity": ctx.get("liquidity_note")},
            }
        )
    if result.cycle:
        for report in _analyst_reports_from_env(result.cycle.blackboard.environment):
            signals.append(
                {
                    "ticker": report.get("symbol", ""),
                    "agent": report.get("analyst", "analyst"),
                    "direction": report.get("direction", ""),
                    "conviction": report.get("conviction"),
                    "summary": report.get("summary", ""),
                    "metrics": report.get("metrics") or {},
                }
            )
    return signals


def _extract_proposals(result: TeamCycleResult) -> list[dict[str, Any]]:
    if not result.cycle:
        return []
    return [p.to_context() for p in result.cycle.blackboard.proposals]
