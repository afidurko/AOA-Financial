"""Background loop runner for the web server and Docker daemon mode."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from aoa.team.orchestrator import TeamCycleResult, TeamOrchestrator


class CycleBusyError(RuntimeError):
    """Raised when a cycle is already in progress."""


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
        self.cycle_seconds_open = team.config.cycle_seconds_market_open
        self.cycle_seconds_closed = team.config.cycle_seconds_market_closed
        self.state = LoopState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._cycle_lock = threading.Lock()

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
        if not self._cycle_lock.acquire(blocking=False):
            raise CycleBusyError("A swarm cycle is already running")
        try:
            result = self.team.run_cycle()
            with self._lock:
                self.state.last_cycle_at = datetime.now(timezone.utc).isoformat()
                self.state.last_result = result
                self.state.cycles_completed += 1
                self.state.last_error = result.halt_reason if result.halted else None
            return result
        except Exception as exc:
            with self._lock:
                self.state.last_error = str(exc)
            raise
        finally:
            self._cycle_lock.release()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if self.team.broker.is_market_open():
                    self.run_once()
            except CycleBusyError:
                pass
            except Exception as exc:  # noqa: BLE001 — background loop must survive
                with self._lock:
                    self.state.last_error = str(exc)
            self._stop.wait(self._effective_cycle_seconds())

    def _effective_cycle_seconds(self) -> int:
        base = self.cycle_seconds
        if self.team.broker.is_market_open() and self.cycle_seconds_open > 0:
            return self.cycle_seconds_open
        if not self.team.broker.is_market_open() and self.cycle_seconds_closed > 0:
            return self.cycle_seconds_closed
        return base
