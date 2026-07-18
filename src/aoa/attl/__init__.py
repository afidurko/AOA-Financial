"""Agentic Task-Team Loop — auto-12 runtime."""

from aoa.attl.critical import CriticalSignal, detect_critical
from aoa.attl.orchestrator import AttlOrchestrator, AttlRunResult

__all__ = [
    "AttlOrchestrator",
    "AttlRunResult",
    "CriticalSignal",
    "detect_critical",
]
