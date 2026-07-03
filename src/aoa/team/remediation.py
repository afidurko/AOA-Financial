"""Aaron's remediation actions for fixable team issues."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from aoa.brokerage.base import Broker
from aoa.team.bob import BobAgent
from aoa.team.models import HealthReport, HealthStatus


@dataclass
class RemediationAction:
    target: str
    action: str
    success: bool
    detail: str

    def to_context(self) -> dict:
        return {
            "target": self.target,
            "action": self.action,
            "success": self.success,
            "detail": self.detail,
        }


@dataclass
class RemediationResult:
    actions: list[RemediationAction] = field(default_factory=list)
    health: HealthReport | None = None
    recovered: bool = False

    def to_context(self) -> dict:
        return {
            "recovered": self.recovered,
            "actions": [a.to_context() for a in self.actions],
            "health": self.health.to_context() if self.health else None,
        }


class TeamRemediator:
    """Deterministic fixes Aaron may apply before escalating to the user."""

    def __init__(self, bob: BobAgent, broker: Broker) -> None:
        self.bob = bob
        self.broker = broker

    def attempt_health_recovery(
        self,
        health: HealthReport,
        *,
        market_cache_clear: Callable[[], None] | None = None,
        max_broker_retries: int = 3,
    ) -> RemediationResult:
        result = RemediationResult(health=health)
        updated_checks = list(health.checks)

        for i, check in enumerate(updated_checks):
            if check.name == "broker" and check.status is HealthStatus.CRITICAL:
                action = self._retry_broker(max_broker_retries)
                result.actions.append(action)
                if action.success:
                    updated_checks[i] = _mark_fixed(check, "Broker reachable after retry.")

            elif check.name == "indicator_pipeline" and check.status is HealthStatus.DEGRADED:
                action = self._clear_market_cache(market_cache_clear)
                result.actions.append(action)
                if action.success:
                    recheck = self.bob._check_indicator_pipeline()  # noqa: SLF001
                    updated_checks[i] = recheck
                    if recheck.status is HealthStatus.OK:
                        result.actions.append(
                            RemediationAction(
                                target="Bob/indicator_pipeline",
                                action="recheck",
                                success=True,
                                detail="Indicator pipeline healthy after cache clear.",
                            )
                        )

        result.health = _rebuild_health(updated_checks)
        result.recovered = result.health.can_proceed and not health.can_proceed
        return result

    def retry_team_member(
        self,
        name: str,
        run_fn: Callable[[], object],
        *,
        expect_count: int = 1,
    ) -> RemediationAction:
        try:
            output = run_fn()
            count = len(output) if isinstance(output, list) else (1 if output else 0)
            success = count >= expect_count
            return RemediationAction(
                target=name,
                action="rerun",
                success=success,
                detail=f"Re-ran {name}; produced {count} result(s).",
            )
        except Exception as exc:  # noqa: BLE001
            return RemediationAction(
                target=name,
                action="rerun",
                success=False,
                detail=f"Re-run failed: {exc}",
            )

    def _retry_broker(self, attempts: int) -> RemediationAction:
        last_error = ""
        for attempt in range(1, attempts + 1):
            try:
                self.broker.get_account()
                return RemediationAction(
                    target="Bob/broker",
                    action="retry_connection",
                    success=True,
                    detail=f"Broker reachable on attempt {attempt}/{attempts}.",
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if attempt < attempts:
                    time.sleep(0.25 * attempt)
        return RemediationAction(
            target="Bob/broker",
            action="retry_connection",
            success=False,
            detail=f"Broker still unreachable after {attempts} attempts: {last_error}",
        )

    def _clear_market_cache(self, clear_fn: Callable[[], None] | None) -> RemediationAction:
        if clear_fn is None:
            return RemediationAction(
                target="Julie/market_cache",
                action="clear_cache",
                success=False,
                detail="No market cache clear hook available.",
            )
        try:
            clear_fn()
            return RemediationAction(
                target="Julie/market_cache",
                action="clear_cache",
                success=True,
                detail="Market data cache cleared.",
            )
        except Exception as exc:  # noqa: BLE001
            return RemediationAction(
                target="Julie/market_cache",
                action="clear_cache",
                success=False,
                detail=f"Cache clear failed: {exc}",
            )


def _mark_fixed(check, detail: str):
    from aoa.team.models import HealthCheck

    return HealthCheck(
        name=check.name,
        status=HealthStatus.OK,
        detail=detail,
        auto_fixed=True,
    )


def _rebuild_health(checks) -> HealthReport:
    critical = any(c.status is HealthStatus.CRITICAL for c in checks)
    degraded = any(c.status is HealthStatus.DEGRADED for c in checks)
    if critical:
        summary = "Critical issues remain after remediation."
    elif degraded:
        summary = "System is degraded but can proceed with caution."
    else:
        summary = "All systems healthy."
    return HealthReport(checks=checks, can_proceed=not critical, summary=summary)
