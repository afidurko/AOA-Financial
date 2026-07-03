"""Bob — systems health, runtime capability, and code integrity checks."""

from __future__ import annotations

import importlib
import sys

from aoa.brokerage.base import Broker
from aoa.config import Config
from aoa.data.indicators import technical_snapshot
from aoa.team.models import HealthCheck, HealthReport, HealthStatus


class BobAgent:
    """Bob does not use the LLM — his checks are deterministic and fast."""

    name = "bob"
    display_name = "Bob"
    role = "Systems Health"

    def __init__(self, config: Config, broker: Broker) -> None:
        self.config = config
        self.broker = broker

    def check_health(self) -> HealthReport:
        checks: list[HealthCheck] = [
            self._check_config(),
            self._check_broker(),
            self._check_core_imports(),
            self._check_indicator_pipeline(),
        ]
        critical = any(c.status is HealthStatus.CRITICAL for c in checks)
        degraded = any(c.status is HealthStatus.DEGRADED for c in checks)
        can_proceed = not critical
        if critical:
            summary = "Critical issues detected — trading cycle should not proceed."
        elif degraded:
            summary = "System is degraded but can proceed with caution."
        else:
            summary = "All systems healthy."
        return HealthReport(checks=checks, can_proceed=can_proceed, summary=summary)

    def _check_config(self) -> HealthCheck:
        problems = self.config.validate()
        if problems:
            return HealthCheck(
                name="configuration",
                status=HealthStatus.CRITICAL,
                detail="; ".join(problems),
            )
        return HealthCheck(
            name="configuration",
            status=HealthStatus.OK,
            detail=f"Config valid ({self.config.trading_mode} mode).",
        )

    def _check_broker(self) -> HealthCheck:
        try:
            acct = self.broker.get_account()
            open_ = self.broker.is_market_open()
            return HealthCheck(
                name="broker",
                status=HealthStatus.OK,
                detail=(
                    f"{self.broker.name} reachable; equity ${acct.equity:,.2f}; "
                    f"market {'open' if open_ else 'closed'}."
                ),
            )
        except Exception as exc:  # noqa: BLE001 — any broker failure is critical
            return HealthCheck(
                name="broker",
                status=HealthStatus.CRITICAL,
                detail=f"Broker unreachable: {exc}",
            )

    def _check_core_imports(self) -> HealthCheck:
        modules = (
            "aoa.agents.base",
            "aoa.swarm.orchestrator",
            "aoa.execution.executor",
            "aoa.risk.guards",
            "aoa.team.orchestrator",
        )
        failed: list[str] = []
        for mod in modules:
            try:
                importlib.import_module(mod)
            except Exception as exc:  # noqa: BLE001 — integrity sweep
                failed.append(f"{mod}: {exc}")
        if failed:
            return HealthCheck(
                name="code_integrity",
                status=HealthStatus.CRITICAL,
                detail="Import failures: " + "; ".join(failed),
            )
        return HealthCheck(
            name="code_integrity",
            status=HealthStatus.OK,
            detail=f"Core modules import cleanly (Python {sys.version_info.major}.{sys.version_info.minor}).",
        )

    def _check_indicator_pipeline(self) -> HealthCheck:
        """Sanity-check that the indicator engine produces expected keys."""
        try:
            from datetime import datetime, timedelta, timezone

            from aoa.brokerage.models import Bar

            base = datetime(2024, 1, 1, tzinfo=timezone.utc)
            bars = []
            price = 100.0
            for i in range(60):
                price *= 1.001
                bars.append(
                    Bar(
                        timestamp=base + timedelta(days=i),
                        open=price * 0.99,
                        high=price * 1.01,
                        low=price * 0.985,
                        close=price,
                        volume=1_000_000,
                    )
                )
            snap = technical_snapshot(bars)
            required = {"sma_20", "rsi_14", "last_close"}
            missing = required - set(snap.keys())
            if missing:
                return HealthCheck(
                    name="indicator_pipeline",
                    status=HealthStatus.DEGRADED,
                    detail=f"Indicator engine missing keys: {', '.join(sorted(missing))}",
                )
            return HealthCheck(
                name="indicator_pipeline",
                status=HealthStatus.OK,
                detail="Indicator pipeline producing expected outputs.",
            )
        except Exception as exc:  # noqa: BLE001
            return HealthCheck(
                name="indicator_pipeline",
                status=HealthStatus.DEGRADED,
                detail=f"Indicator self-test failed: {exc}",
            )
