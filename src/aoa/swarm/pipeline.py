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
        bus = ctx.blackboard.events
        for stage in self.stages:
            bus.emit("stage.start", stage.name)
            ctx.journal.record("pipeline.stage.start", {"stage": stage.name})
            continue_cycle = stage.run(ctx)
            if stage.checkpoint:
                ctx.blackboard.environment.checkpoint(stage.name)
                bus.emit("stage.checkpoint", stage.name, {"stage": stage.name})
            bus.emit("stage.complete", stage.name)
            ctx.journal.record("pipeline.stage.complete", {"stage": stage.name})
            if not continue_cycle:
                break

    def run_until(self, ctx: CycleContext, stop_before: str) -> None:
        """Run stages up to (but not including) ``stop_before`` — for edit workflows."""
        for stage in self.stages:
            if stage.name == stop_before:
                break
            bus = ctx.blackboard.events
            bus.emit("stage.start", stage.name)
            continue_cycle = stage.run(ctx)
            if stage.checkpoint:
                ctx.blackboard.environment.checkpoint(stage.name)
                bus.emit("stage.checkpoint", stage.name, {"stage": stage.name})
            bus.emit("stage.complete", stage.name)
            if not continue_cycle:
                break
