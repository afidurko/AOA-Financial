"""The five-member agent team that coordinates the trading swarm."""

from aoa.team.aaron import AaronAgent
from aoa.team.alan import AlanAgent
from aoa.team.bob import BobAgent
from aoa.team.julie import JulieAgent
from aoa.team.models import (
    AlgorithmReport,
    CEOReport,
    DecisionBrief,
    HealthReport,
    HealthStatus,
    TeamMemberStatus,
    TrendDirection,
    TrendReport,
)
from aoa.team.orchestrator import TeamCycleResult, TeamOrchestrator
from aoa.team.tom import TomAgent

__all__ = [
    "AaronAgent",
    "AlanAgent",
    "AlgorithmReport",
    "BobAgent",
    "CEOReport",
    "DecisionBrief",
    "HealthReport",
    "HealthStatus",
    "JulieAgent",
    "TeamCycleResult",
    "TeamMemberStatus",
    "TeamOrchestrator",
    "TomAgent",
    "TrendDirection",
    "TrendReport",
]
