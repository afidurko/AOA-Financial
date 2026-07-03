"""Swarm orchestration: the blackboard and the cycle orchestrator."""

from aoa.swarm.blackboard import Blackboard
from aoa.swarm.environment import DomainSlice, MeshedView, SwarmEnvironment
from aoa.swarm.events import EventBus, SwarmEvent

__all__ = [
    "Blackboard",
    "CycleContext",
    "DomainSlice",
    "EventBus",
    "MeshedView",
    "Orchestrator",
    "Pipeline",
    "PipelineStage",
    "SwarmEnvironment",
    "SwarmEvent",
    "AgentTeam",
]


def __getattr__(name: str):
    if name == "Orchestrator":
        from aoa.swarm.orchestrator import Orchestrator

        return Orchestrator
    if name == "CycleContext":
        from aoa.swarm.context import CycleContext

        return CycleContext
    if name == "Pipeline":
        from aoa.swarm.pipeline import Pipeline

        return Pipeline
    if name == "PipelineStage":
        from aoa.swarm.pipeline import PipelineStage

        return PipelineStage
    if name == "AgentTeam":
        from aoa.swarm.team import AgentTeam

        return AgentTeam
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
