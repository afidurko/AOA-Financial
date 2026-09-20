"""Connectome-driven signal engine.

A biologically-inspired lane that maps market *sensory* inputs through a
weighted neural connectome to *motor* outputs (buy / sell / hold drives).

* :mod:`aoa.connectome.engine` — the generic accumulate-and-fire propagation
  engine with motor-group readout and reward-modulated plasticity.
* :mod:`aoa.connectome.elegans` — a curated C. elegans sub-connectome (touch
  and chemotaxis circuits) mapped onto market features: food gradient ≈
  positive momentum, nose touch ≈ drawdown shock, forward locomotion ≈ long
  exposure, reversal ≈ exit.

Research/backtest lane only — no live order path.
"""

from aoa.connectome.elegans import MarketWorm, MotorDecision, build_market_worm
from aoa.connectome.engine import Connectome, FireEvent, MotorReadout

__all__ = [
    "Connectome",
    "FireEvent",
    "MotorReadout",
    "MarketWorm",
    "MotorDecision",
    "build_market_worm",
]
