"""Background loop runner for the web server and Docker daemon mode."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from aoa.swarm.orchestrator import CycleResult, Orchestrator


@dataclass
class LoopState:
    running: bool = False
    last_cycle_at: str | None = None
    last_error: str | None = None
    cycles_completed: int = 0
    last_result: CycleResult | None = None


class LoopRunner:
    """Runs ``Orchestrator.run_cycle()`` on a background thread."""

    def __init__(self, orchestrator: Orchestrator, cycle_seconds: int) -> None:
        self.orchestrator = orchestrator
        self.cycle_seconds = cycle_seconds
        self.state = LoopState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

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

    def run_once(self) -> CycleResult:
        result = self.orchestrator.run_cycle()
        self.state.last_cycle_at = datetime.now(timezone.utc).isoformat()
        self.state.last_result = result
        self.state.cycles_completed += 1
        self.state.last_error = None
        return result

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self.orchestrator.broker.is_market_open():
                    self.run_once()
            except Exception as exc:  # noqa: BLE001 — background loop must survive
                self.state.last_error = str(exc)
            self._stop.wait(self.cycle_seconds)
