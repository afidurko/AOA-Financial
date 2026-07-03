"""Interval scheduler — chain completed work loops with fresh discovery."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from aoa.config import Config
from aoa.workloop.approval import ApprovalRequired, check_approval
from aoa.workloop.orchestrator import WorkloopOrchestrator, WorkloopResult
from aoa.workloop.store import WorkloopStore


SleepFn = Callable[[float], None]


@dataclass
class SchedulerState:
    iteration: int = 0
    last_completed_run_id: str = ""
    last_completed_at: str = ""
    next_run_at: str = ""
    status: str = "idle"  # idle | running | awaiting_approval | sleeping


@dataclass
class LoopIterationResult:
    result: WorkloopResult
    action: str  # completed | awaiting_approval | failed | resumed
    iteration: int = 0


class WorkloopScheduler:
    """Runs work loops continuously at a fixed interval after each completion."""

    def __init__(
        self,
        orchestrator: WorkloopOrchestrator,
        *,
        interval_seconds: int,
        sleep_fn: SleepFn | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.interval_seconds = max(60, interval_seconds)
        self.sleep = sleep_fn or time.sleep
        self.store: WorkloopStore = orchestrator.store

    def state(self) -> SchedulerState:
        raw = self.store.load_scheduler()
        return SchedulerState(
            iteration=int(raw.get("iteration", 0)),
            last_completed_run_id=str(raw.get("last_completed_run_id", "")),
            last_completed_at=str(raw.get("last_completed_at", "")),
            next_run_at=str(raw.get("next_run_at", "")),
            status=str(raw.get("status", "idle")),
        )

    def run_forever(self, *, dry_run: bool = False) -> None:
        """Run work loops on an interval until interrupted."""
        self.store.record(
            "workloop.scheduler.start",
            {"interval_seconds": self.interval_seconds, "dry_run": dry_run},
        )
        try:
            while True:
                tick = self.tick(dry_run=dry_run)
                if tick.action == "completed":
                    self._sleep_until_next()
                elif tick.action == "awaiting_approval":
                    self._sleep_until_next()
                elif tick.action == "failed":
                    self._sleep_until_next()
                else:
                    # Resumed and finished in one tick — still pace the next cycle.
                    if tick.result.run.status == "completed":
                        self._sleep_until_next()
        except KeyboardInterrupt:
            self._persist_scheduler(status="idle")
            self.store.record("workloop.scheduler.stop", {"reason": "keyboard_interrupt"})

    def tick(self, *, dry_run: bool = False) -> LoopIterationResult:
        """Execute one scheduler step: resume, fresh run, or approval poll."""
        sched = self.state()
        existing = self.store.load_run()

        if existing is not None and existing.status == "awaiting_approval":
            return self._tick_awaiting_approval(existing, sched, dry_run=dry_run)

        if existing is not None and existing.status == "completed":
            self._finalize_completed(existing, sched)
            existing = None

        if existing is not None and existing.status == "failed":
            self.store.clear_run()
            self._persist_scheduler(status="idle", iteration=sched.iteration)

        sched = self.state()
        self._persist_scheduler(status="running", iteration=sched.iteration + 1)
        result = self.orchestrator.run(
            dry_run=dry_run,
            iteration=sched.iteration + 1,
            previous_run_id=sched.last_completed_run_id,
        )

        if result.halted and result.run.status == "awaiting_approval":
            self._persist_scheduler(status="awaiting_approval", iteration=sched.iteration + 1)
            return LoopIterationResult(
                result=result,
                action="awaiting_approval",
                iteration=sched.iteration + 1,
            )

        if result.run.status == "completed":
            self._finalize_completed(result.run, self.state())
            return LoopIterationResult(
                result=result,
                action="completed",
                iteration=result.run.iteration,
            )

        self._persist_scheduler(status="idle", iteration=sched.iteration + 1)
        return LoopIterationResult(
            result=result,
            action="failed",
            iteration=sched.iteration + 1,
        )

    def _tick_awaiting_approval(self, existing, sched: SchedulerState, *, dry_run: bool) -> LoopIterationResult:
        try:
            check_approval(
                self.store,
                run_id=existing.run_id,
                approver=self.orchestrator.config.workloop_approver,
            )
        except ApprovalRequired:
            self._persist_scheduler(status="awaiting_approval", iteration=existing.iteration or sched.iteration)
            return LoopIterationResult(
                result=WorkloopResult(run=existing, halted=True, notes=list(existing.notes)),
                action="awaiting_approval",
                iteration=existing.iteration or sched.iteration,
            )

        self._persist_scheduler(status="running", iteration=existing.iteration or sched.iteration)
        result = self.orchestrator.run(resume=True, from_stage="approval", dry_run=dry_run)
        if result.run.status == "completed":
            self._finalize_completed(result.run, self.state())
            return LoopIterationResult(
                result=result,
                action="resumed",
                iteration=result.run.iteration,
            )
        self._persist_scheduler(status="idle", iteration=existing.iteration or sched.iteration)
        return LoopIterationResult(
            result=result,
            action="failed",
            iteration=existing.iteration or sched.iteration,
        )

    def _finalize_completed(self, run, sched: SchedulerState) -> None:
        now = datetime.now(timezone.utc)
        next_at = now + timedelta(seconds=self.interval_seconds)
        iteration = run.iteration or (sched.iteration + 1)
        self.store.record(
            "workloop.scheduler.completed",
            {
                "run_id": run.run_id,
                "iteration": iteration,
                "previous_run_id": run.previous_run_id,
            },
        )
        self.store.clear_run()
        self.store.save_scheduler(
            {
                "iteration": iteration,
                "last_completed_run_id": run.run_id,
                "last_completed_at": now.isoformat(),
                "next_run_at": next_at.isoformat(),
                "status": "sleeping",
            }
        )

    def _sleep_until_next(self) -> None:
        sched = self.state()
        if sched.next_run_at:
            try:
                target = datetime.fromisoformat(sched.next_run_at)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                remaining = (target - datetime.now(timezone.utc)).total_seconds()
                if remaining > 0:
                    self.sleep(remaining)
                    return
            except ValueError:
                pass
        self.sleep(self.interval_seconds)

    def _persist_scheduler(self, *, status: str, iteration: int | None = None) -> None:
        sched = self.state()
        data = {
            "iteration": iteration if iteration is not None else sched.iteration,
            "last_completed_run_id": sched.last_completed_run_id,
            "last_completed_at": sched.last_completed_at,
            "next_run_at": sched.next_run_at,
            "status": status,
        }
        self.store.save_scheduler(data)


def build_scheduler(config: Config, *, repo_root=None) -> WorkloopScheduler:
    orch = WorkloopOrchestrator(config, repo_root=repo_root)
    return WorkloopScheduler(
        orch,
        interval_seconds=config.workloop_interval_seconds,
    )
