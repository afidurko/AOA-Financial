"""Composable pipeline — declarative stage graph for one swarm cycle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from aoa.swarm.context import CycleContext


@dataclass
class PipelineStage(ABC):
    """One step in the analysis → decision → execution cycle."""

    name: str
    checkpoint: bool = False

    @abstractmethod
    def run(self, ctx: CycleContext) -> bool:
        """Execute the stage. Return False to halt the pipeline early."""


@dataclass
class Pipeline:
    """Runs an ordered list of stages with journal emission."""

    stages: list[PipelineStage] = field(default_factory=list)

    def run(self, ctx: CycleContext) -> None:
        for stage in self.stages:
            ctx.journal.record("pipeline.stage.start", {"stage": stage.name})
            continue_cycle = stage.run(ctx)
            ctx.journal.record("pipeline.stage.complete", {"stage": stage.name})
            if not continue_cycle:
                break

    def run_until(self, ctx: CycleContext, stop_before: str) -> None:
        """Run stages up to (but not including) ``stop_before``."""
        for stage in self.stages:
            if stage.name == stop_before:
                break
            ctx.journal.record("pipeline.stage.start", {"stage": stage.name})
            continue_cycle = stage.run(ctx)
            ctx.journal.record("pipeline.stage.complete", {"stage": stage.name})
            if not continue_cycle:
                break
