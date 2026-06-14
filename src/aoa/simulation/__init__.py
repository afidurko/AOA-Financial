"""Market-trend analysis and Monte-Carlo scenario simulation.

This package turns a real bar history into (a) a description of *what already
happened* (:mod:`~aoa.simulation.trends`) and (b) reproducible *what-could-happen*
projections — both random (:class:`~aoa.simulation.simulator.MarketSimulator`)
and deterministic scenario replays (:mod:`~aoa.simulation.scenarios`).
"""

from aoa.simulation.live import LiveMarketTracker, LiveUpdate
from aoa.simulation.scenarios import (
    SCENARIO_LIBRARY,
    Scenario,
    extract_scenario,
    get_scenario,
    list_scenarios,
    synthesize,
)
from aoa.simulation.simulator import (
    MarketSimulator,
    SimulationConfig,
    SimulationResult,
    StressResult,
)
from aoa.simulation.trends import (
    DrawdownEvent,
    ReturnStats,
    TrendAnalysis,
    analyze_trends,
    drawdown_events,
    max_drawdown,
    return_stats,
)

__all__ = [
    # trends
    "analyze_trends",
    "TrendAnalysis",
    "ReturnStats",
    "DrawdownEvent",
    "drawdown_events",
    "max_drawdown",
    "return_stats",
    # scenarios
    "Scenario",
    "SCENARIO_LIBRARY",
    "list_scenarios",
    "get_scenario",
    "extract_scenario",
    "synthesize",
    # simulator
    "MarketSimulator",
    "SimulationConfig",
    "SimulationResult",
    "StressResult",
    # live
    "LiveMarketTracker",
    "LiveUpdate",
]
