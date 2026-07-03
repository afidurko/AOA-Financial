"""Composable pipeline — declarative stage graph for one swarm cycle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from aoa.swarm.context import CycleContext


@dataclass
class PipelineStage(ABC):
    """One step in the analysis → decision → execution cycle."""

    name: str
    checkpoint: bool = False  # snapshot environment after this stage for editing

    @abstractmethod
    def run(self, ctx: CycleContext) -> bool:
        """Execute the stage. Return False to halt the pipeline early."""


@dataclass
class Pipeline:
    """Runs an ordered list of stages with event emission and checkpoints."""

    stages: list[PipelineStage] = field(default_factory=list)

    def run(self, ctx: CycleContext) -> None:
        self._run_stages(ctx)

    def run_until(self, ctx: CycleContext, stop_before: str) -> None:
        """Run stages up to (but not including) ``stop_before`` — for edit workflows."""
        self._run_stages(ctx, stop_before=stop_before)

    def run_from(self, ctx: CycleContext, start_at: str) -> None:
        """Run stages starting at ``start_at`` (inclusive)."""
        self._run_stages(ctx, start_at=start_at)

    def _run_stages(
        self,
        ctx: CycleContext,
        *,
        stop_before: str | None = None,
        start_at: str | None = None,
    ) -> None:
        started = start_at is None
        for stage in self.stages:
            if not started:
                if stage.name == start_at:
                    started = True
                else:
                    continue
            if stop_before is not None and stage.name == stop_before:
                break
            if not self._run_stage(ctx, stage):
                break

    def _run_stage(self, ctx: CycleContext, stage: PipelineStage) -> bool:
        bus = ctx.blackboard.events
        bus.emit("stage.start", stage.name)
        ctx.journal.record("pipeline.stage.start", {"stage": stage.name})
        continue_cycle = stage.run(ctx)
        if stage.checkpoint:
            ctx.blackboard.environment.checkpoint(stage.name)
            bus.emit("stage.checkpoint", stage.name, {"stage": stage.name})
        bus.emit("stage.complete", stage.name)
        ctx.journal.record("pipeline.stage.complete", {"stage": stage.name})
        return continue_cycle
