"""ROI / cost-basis sizing helpers for aoa_financial swarm decisions."""

from __future__ import annotations

from aoa_financial.config import Config
from aoa_financial.swarm.agents import AgentSignal
from aoa_financial.swarm.decision import (
    _roi_edge_quality,
    decide,
    forecast_roi_edges,
)


def _bull_signals() -> list[AgentSignal]:
    return [
        AgentSignal(agent="technical", score=0.8, confidence=0.8, rationale="t"),
        AgentSignal(agent="forecast", score=0.7, confidence=0.7, rationale="f"),
        AgentSignal(agent="regime", score=0.6, confidence=0.8, rationale="r"),
    ]


def test_forecast_p10_p90_are_converted_from_prices_to_returns():
    fc = {
        "last_price": 100.0,
        "expected_return": 0.05,
        "p10": 90.0,   # -10% return
        "p90": 120.0,  # +20% return
        "confidence": 0.7,
    }
    roi = forecast_roi_edges(fc, cost_pct=0.01)
    assert abs(roi["p10_return"] - (-0.10)) < 1e-9
    assert abs(roi["p90_return"] - 0.20) < 1e-9
    assert abs(roi["net_expected_return"] - 0.04) < 1e-9
    # Long: net +4% / left-tail loss 11% (10% + 1% cost)
    assert abs(roi["roi_edge_long"] - (0.04 / 0.11)) < 1e-9
    # Short: net -4% expected / right-tail loss 19% (20% - 1% cost on short side wait)
    # short expected = -net_expected = -0.04
    # tail_loss_short = max(0, net_p90) = max(0, 0.20 - 0.01) = 0.19
    assert abs(roi["roi_edge_short"] - (-0.04 / 0.19)) < 1e-9


def test_roi_edge_quality_mapping():
    assert _roi_edge_quality(-1.0) == 0.0
    assert _roi_edge_quality(0.0) == 0.0
    assert abs(_roi_edge_quality(1.0) - 0.5) < 1e-9
    assert _roi_edge_quality(1e9) > 0.99


def test_decide_without_roi_edges_preserves_legacy_sizing():
    d = decide("TEST", _bull_signals())
    assert d.action == "BUY"
    assert d.roi_quality == 1.0
    assert d.exposure_multiplier == 1.0
    # Legacy formula: |conviction| * confidence * 0.25, capped at 0.15
    expected = min(0.15, abs(d.conviction) * d.confidence * 0.25)
    assert abs(d.target_weight - expected) < 1e-9
    assert d.target_weight > 0


def test_decide_scales_weight_by_roi_quality():
    base = decide("TEST", _bull_signals())
    weak = decide(
        "TEST",
        _bull_signals(),
        roi_edge_long=0.1,
        forecast_confidence=1.0,
        net_expected_return=0.01,
    )
    assert weak.action == "BUY"
    assert 0 < weak.roi_quality < 1
    assert weak.target_weight < base.target_weight
    assert abs(weak.target_weight - base.target_weight * weak.roi_quality) < 1e-9


def test_config_cost_defaults_are_zero():
    cfg = Config()
    assert cfg.transaction_cost_pct == 0.0
    assert cfg.slippage_pct == 0.0
