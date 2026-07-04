"""Idle opportunity sweep — self-scheduled market analysis when nothing else fired."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from aoa.notify.policy import NotificationPolicy

if TYPE_CHECKING:
    from aoa.team.orchestrator import OpportunitySweepResult, TeamCycleResult, TeamOrchestrator


@dataclass
class SweepState:
    enabled: bool = True
    idle_seconds: float = 0.0
    threshold_seconds: int = 900
    last_activity_at: str | None = None
    last_sweep_at: str | None = None
    sweeps_completed: int = 0
    last_opportunities_found: int = 0
    last_error: str | None = None
    sweep_running: bool = False


class SweepActivityTracker:
    """Tracks when alerts or opportunity notifications last reset the idle timer."""

    def __init__(self, *, threshold_seconds: int = 900) -> None:
        self.threshold_seconds = threshold_seconds
        self._lock = threading.Lock()
        self._last_activity_monotonic = time.monotonic()
        self._last_activity_at = datetime.now(timezone.utc).isoformat()

    def record_activity(self) -> None:
        with self._lock:
            self._last_activity_monotonic = time.monotonic()
            self._last_activity_at = datetime.now(timezone.utc).isoformat()

    def seconds_idle(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_activity_monotonic

    @property
    def last_activity_at(self) -> str:
        with self._lock:
            return self._last_activity_at

    def is_idle(self) -> bool:
        return self.seconds_idle() >= self.threshold_seconds

    def record_cycle_result(self, result: TeamCycleResult, policy: NotificationPolicy) -> None:
        notes = policy.evaluate_cycle(result)
        if policy.had_meaningful_activity(notes):
            self.record_activity()
            return
        if result.cycle and any(p.approved for p in result.cycle.blackboard.proposals):
            self.record_activity()


class OpportunitySweepLoop:
    """Background timer that runs a market analysis swarm after prolonged idle."""

    def __init__(
        self,
        team: TeamOrchestrator,
        *,
        enabled: bool = True,
        threshold_seconds: int = 900,
        poll_seconds: int = 60,
        cycle_lock: threading.Lock | None = None,
    ) -> None:
        self.team = team
        self.enabled = enabled
        self.poll_seconds = poll_seconds
        self.tracker = SweepActivityTracker(threshold_seconds=threshold_seconds)
        self._cycle_lock = cycle_lock or threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.state = SweepState(enabled=enabled, threshold_seconds=threshold_seconds)

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="aoa-opportunity-sweep",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._thread is not None:
                self._thread.join(timeout=5)
                self._thread = None

    def record_cycle_result(self, result: TeamCycleResult) -> None:
        self.tracker.record_cycle_result(result, self.team.notify_policy)

    def run_sweep_now(self) -> OpportunitySweepResult:
        return self._execute_sweep()

    def snapshot_state(self) -> SweepState:
        with self._lock:
            self.state.idle_seconds = self.tracker.seconds_idle()
            self.state.last_activity_at = self.tracker.last_activity_at
            return SweepState(
                enabled=self.state.enabled,
                idle_seconds=self.state.idle_seconds,
                threshold_seconds=self.state.threshold_seconds,
                last_activity_at=self.state.last_activity_at,
                last_sweep_at=self.state.last_sweep_at,
                sweeps_completed=self.state.sweeps_completed,
                last_opportunities_found=self.state.last_opportunities_found,
                last_error=self.state.last_error,
                sweep_running=self.state.sweep_running,
            )

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if (
                    self.team.broker.is_market_open()
                    and self.tracker.is_idle()
                    and self._cycle_lock.acquire(blocking=False)
                ):
                    try:
                        self._execute_sweep()
                    finally:
                        self._cycle_lock.release()
            except Exception as exc:  # noqa: BLE001 — background loop must survive
                with self._lock:
                    self.state.last_error = str(exc)
            self._stop.wait(self.poll_seconds)

    def _execute_sweep(self) -> OpportunitySweepResult:
        with self._lock:
            self.state.sweep_running = True
        try:
            sweep = self.team.run_opportunity_sweep()
            with self._lock:
                self.state.last_sweep_at = datetime.now(timezone.utc).isoformat()
                self.state.sweeps_completed += 1
                self.state.last_opportunities_found = sweep.opportunities_notified
                self.state.last_error = None
            self.tracker.record_activity()
            return sweep
        except Exception as exc:
            with self._lock:
                self.state.last_error = str(exc)
            raise
        finally:
            with self._lock:
                self.state.sweep_running = False
