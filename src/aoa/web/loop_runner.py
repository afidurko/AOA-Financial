"""Background loop runner for the web server and Docker daemon mode."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from aoa.team.orchestrator import TeamCycleResult, TeamOrchestrator


@dataclass
class LoopState:
    running: bool = False
    last_cycle_at: str | None = None
    last_error: str | None = None
    cycles_completed: int = 0
    last_result: TeamCycleResult | None = None


class LoopRunner:
    """Runs ``TeamOrchestrator.run_cycle()`` on a background thread."""

    def __init__(self, team: TeamOrchestrator, cycle_seconds: int) -> None:
        self.team = team
        self.cycle_seconds = cycle_seconds
        self.state = LoopState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def broker(self):
        return self.team.broker

    @property
    def journal(self):
        return self.team.journal

    def start(self) -> None:
        with self._lock:
            if self.state.running:
                return
            self._stop.clear()
            self.state.running = True
            self._thread = threading.Thread(target=self._run, name="aoa-loop", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._thread is not None:
                self._thread.join(timeout=5)
                self._thread = None
            self.state.running = False

    def run_once(self) -> TeamCycleResult:
        result = self.team.run_cycle()
        self.state.last_cycle_at = datetime.now(timezone.utc).isoformat()
        self.state.last_result = result
        self.state.cycles_completed += 1
        self.state.last_error = result.halt_reason if result.halted else None
        return result

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self.team.broker.is_market_open():
                    self.run_once()
            except Exception as exc:  # noqa: BLE001 — background loop must survive
                self.state.last_error = str(exc)
            self._stop.wait(self.cycle_seconds)
