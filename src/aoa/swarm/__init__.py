"""Swarm orchestration: the blackboard and the cycle orchestrator."""

from aoa.swarm.blackboard import Blackboard
from aoa.swarm.environment import DomainSlice, MeshedView, SwarmEnvironment

__all__ = [
    "Blackboard",
    "DomainSlice",
    "MeshedView",
    "Orchestrator",
    "SwarmEnvironment",
]


def __getattr__(name: str):
    if name == "Orchestrator":
        from aoa.swarm.orchestrator import Orchestrator

        return Orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
