"""Tests for the meshing agent and editable swarm environment."""

from __future__ import annotations

from aoa.agents.base import Direction, Signal
from aoa.agents.meshing import MeshingAgent, _combine
from aoa.swarm.environment import MeshedView, SwarmEnvironment
from tests.conftest import FakeLLM


def test_combine_corroborated_signals():
    tech = Signal("AAPL", "technical", Direction.BULLISH, 0.8, "x")
    fund = Signal("AAPL", "fundamental", Direction.BULLISH, 0.6, "y")
    direction, conv = _combine(tech, fund)
    assert direction is Direction.BULLISH
    assert conv > 0.8


def test_combine_conflicting_signals_discounts():
    tech = Signal("AAPL", "technical", Direction.BULLISH, 0.8, "x")
    fund = Signal("AAPL", "fundamental", Direction.BEARISH, 0.6, "y")
    direction, conv = _combine(tech, fund)
    assert direction is Direction.BULLISH
    assert conv < 0.8


def test_meshing_agent_produces_meshed_view():
    llm = FakeLLM()
    agent = MeshingAgent(llm)
    tech = Signal("AAPL", "technical", Direction.BULLISH, 0.75, "uptrend")
    fund = Signal("AAPL", "fundamental", Direction.BULLISH, 0.6, "stable")

    view = agent.mesh("AAPL", [tech, fund], scanner_reason="pullback")

    assert view.symbol == "AAPL"
    assert view.direction is Direction.BULLISH
    assert view.conviction > 0
    assert len(view.source_signals) == 2
    assert view.to_signal().source == "meshing"


def test_meshed_view_editable_without_touching_domains():
    view = MeshedView(
        symbol="AAPL",
        direction=Direction.BULLISH,
        conviction=0.7,
        rationale="base",
    )
    view.edit(direction="neutral", conviction=0.2, rationale="manual override")

    assert view.direction is Direction.BULLISH  # base unchanged
    assert view.effective_direction is Direction.NEUTRAL
    assert view.effective_conviction == 0.2
    assert view.effective_rationale == "manual override"


def test_swarm_environment_domain_and_global_edits():
    env = SwarmEnvironment(global_context={"equity": 100_000})
    env.set_domain("technical:AAPL", {"signal": {"direction": "bullish", "conviction": 0.8}})

    env.edit_domain("technical:AAPL", signal={"direction": "neutral", "conviction": 0.3})
    effective = env.domains["technical:AAPL"].effective()
    assert effective["signal"]["direction"] == "neutral"

    env.edit_global(commentary="cycle note")
    assert env.effective_global()["commentary"] == "cycle note"
    assert env.effective_global()["equity"] == 100_000


def test_swarm_environment_per_symbol_context():
    env = SwarmEnvironment()
    env.set_domain("scanner", {"by_symbol": {"AAPL": {"reason": "momentum"}}})
    env.set_meshed(
        MeshedView(
            symbol="AAPL",
            direction=Direction.BULLISH,
            conviction=0.65,
            rationale="aligned",
        )
    )
    env.set_domain("options:AAPL", {"strategy": "long_call", "contract_symbol": "X"})

    ctx = env.per_symbol_context()
    assert len(ctx) == 1
    assert ctx[0]["symbol"] == "AAPL"
    assert ctx[0]["scanner_reason"] == "momentum"
    assert ctx[0]["meshed_view"]["direction"] == "bullish"
    assert ctx[0]["options_idea"]["strategy"] == "long_call"
