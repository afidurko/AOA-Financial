"""Agentic Task-Team Loop — auto-12 runtime."""

from aoa.attl.critical import CriticalSignal, detect_critical
from aoa.attl.mesh import MeshController, MeshSnapshot
from aoa.attl.orchestrator import AttlOrchestrator, AttlRunResult

__all__ = [
    "AttlOrchestrator",
    "AttlRunResult",
    "CriticalSignal",
    "MeshController",
    "MeshSnapshot",
    "detect_critical",
]
