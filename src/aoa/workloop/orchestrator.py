"""Work-loop orchestrator — runs the discover→merge improvement cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aoa.config import Config
from aoa.workloop.models import STAGE_ORDER, WorkloopRun
from aoa.workloop.stages import WorkloopContext, WorkloopStage, default_stages, stage_index
from aoa.workloop.store import WorkloopStore


@dataclass
class WorkloopResult:
    run: WorkloopRun
    halted: bool = False
    notes: list[str] = field(default_factory=list)


class WorkloopOrchestrator:
    def __init__(
        self,
        config: Config,
        *,
        store: WorkloopStore | None = None,
        stages: list[WorkloopStage] | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.config = config
        self.store = store or WorkloopStore(config.workloop_path)
        self.stages = stages or default_stages()
        self.repo_root = repo_root or Path.cwd()

    def run(
        self,
        *,
        from_stage: str | None = None,
        dry_run: bool = False,
        resume: bool = False,
    ) -> WorkloopResult:
        run = self._resolve_run(resume=resume)
        start_idx = stage_index(from_stage) if from_stage else stage_index(run.stage)
        ctx = WorkloopContext(
            config=self.config,
            store=self.store,
            run=run,
            repo_root=self.repo_root,
            dry_run=dry_run,
        )
        self.store.record(
            "workloop.start",
            {"run_id": run.run_id, "from_stage": run.stage, "dry_run": dry_run},
        )

        halted = False
        for stage in self.stages[start_idx:]:
            run.stage = stage.name
            run.status = "running"
            self.store.save_run(run)
            self.store.record("workloop.stage.start", {"stage": stage.name, "run_id": run.run_id})

            ok = stage.run(ctx)
            self.store.record(
                "workloop.stage.complete",
                {"stage": stage.name, "run_id": run.run_id, "ok": ok},
            )
            self.store.save_run(run)

            if not ok:
                halted = True
                break

            next_idx = stage_index(stage.name) + 1
            if next_idx < len(STAGE_ORDER):
                run.stage = STAGE_ORDER[next_idx]

        if not halted:
            if run.status != "completed":
                run.status = "completed"
            self.store.save_run(run)
            self.store.record("workloop.complete", {"run_id": run.run_id})

        return WorkloopResult(run=run, halted=halted, notes=list(run.notes))

    def status(self) -> WorkloopRun | None:
        return self.store.load_run()

    def approve(self, *, approver: str, note: str = "") -> dict:
        run = self.store.load_run()
        if run is None:
            run_id = self.store.new_run_id()
        else:
            run_id = run.run_id
        from aoa.workloop.approval import record_approval

        return record_approval(
            self.store,
            run_id=run_id,
            approver=approver,
            note=note,
        )

    def _resolve_run(self, *, resume: bool) -> WorkloopRun:
        if resume:
            existing = self.store.load_run()
            if existing is not None:
                existing.status = "running"
                existing.error = ""
                return existing
        return WorkloopRun(run_id=self.store.new_run_id())
