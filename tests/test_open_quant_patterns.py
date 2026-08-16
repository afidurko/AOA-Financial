"""Tests for open-quant-live-book pattern helpers (research reference)."""

from __future__ import annotations

import math

import pytest

from aoa.research.open_quant_patterns import (
    coupled_ar_series,
    cov_from_returns,
    equal_risk_contribution,
    inverse_vol_weights,
    linear_granger_causality,
    mutual_information_stats,
    net_information_flow,
    risk_contributions,
    shannon_entropy,
    synthetic_smoke,
)


def test_inverse_vol_weights_two_assets() -> None:
    w = inverse_vol_weights((0.20, 0.10))
    assert abs(sum(w) - 1.0) < 1e-12
    assert abs(w[0] - 1.0 / 3.0) < 1e-12
    assert abs(w[1] - 2.0 / 3.0) < 1e-12


def test_equal_risk_contribution_uncorrelated() -> None:
    cov = [[0.04, 0.0], [0.0, 0.01]]
    res = equal_risk_contribution(cov)
    assert abs(sum(res.weights) - 1.0) < 1e-8
    assert abs(res.weights[0] - 1.0 / 3.0) < 1e-4
    assert abs(res.weights[1] - 2.0 / 3.0) < 1e-4
    assert abs(res.risk_fractions[0] - 0.5) < 1e-3
    assert abs(res.risk_fractions[1] - 0.5) < 1e-3


def test_equal_risk_contribution_correlated() -> None:
    cov = [[0.04, 0.015], [0.015, 0.01]]
    res = equal_risk_contribution(cov)
    assert abs(sum(res.weights) - 1.0) < 1e-8
    assert abs(res.risk_fractions[0] - 0.5) < 1e-3
    assert abs(res.risk_fractions[1] - 0.5) < 1e-3
    rc = risk_contributions(cov, res.weights)
    total = sum(rc)
    assert abs(rc[0] / total - 0.5) < 1e-3


def test_equal_risk_contribution_custom_budget() -> None:
    cov = [[0.04, 0.0], [0.0, 0.01]]
    res = equal_risk_contribution(cov, budget=(0.25, 0.75))
    assert abs(res.risk_fractions[0] - 0.25) < 1e-2
    assert abs(res.risk_fractions[1] - 0.75) < 1e-2


def test_shannon_entropy_constant_is_zero() -> None:
    assert shannon_entropy([1.0] * 50, bins=5) == 0.0


def test_mutual_information_identical_series() -> None:
    xs = [float(i % 7) for i in range(100)]
    stats = mutual_information_stats(xs, xs, bins=7)
    assert stats.mutual_information > 0.5
    assert 0.0 <= stats.global_correlation <= 1.0
    # I(X;X) ≈ H(X); joint ≈ H(X)
    assert abs(stats.mutual_information - stats.entropy_x) < 0.05
    assert abs(stats.joint_entropy - stats.entropy_x) < 0.05


def test_mutual_information_rejects_bad_bins() -> None:
    with pytest.raises(ValueError, match="bins"):
        mutual_information_stats([1.0, 2.0], [1.0, 2.0], bins=1)
    with pytest.raises(ValueError, match="bins"):
        shannon_entropy([1.0, 2.0], bins=0)


def test_linear_granger_detects_cause() -> None:
    x, y = coupled_ar_series(300, seed=42, ar_x=0.5, coupling=0.8)
    xy = linear_granger_causality(x, y, lags=1)
    yx = linear_granger_causality(y, x, lags=1)
    assert xy.gc > yx.gc
    assert abs(xy.transfer_entropy - xy.gc / 2.0) < 1e-12


def test_net_information_flow_direction() -> None:
    x, y = coupled_ar_series(250, seed=7, ar_x=0.4, coupling=0.7)
    flow = net_information_flow(x, y, lags=1)
    assert flow.dominant == "x->y"
    assert flow.net_xy > 0


def test_cov_from_returns_shape() -> None:
    returns = [[0.01, -0.02, 0.03, 0.0], [0.0, 0.01, -0.01, 0.02]]
    cov = cov_from_returns(returns)
    assert len(cov) == 2 and len(cov[0]) == 2
    assert cov[0][0] > 0 and cov[1][1] > 0
    assert abs(cov[0][1] - cov[1][0]) < 1e-12


def test_synthetic_smoke_ok() -> None:
    result = synthetic_smoke(seed=7)
    assert result["ok"] is True
    assert result["never_live"] is True
    assert result["companion"] == "open-quant-live-book"
    assert abs(result["erc_risk_fractions"][0] - 0.5) < 1e-3


def test_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        inverse_vol_weights(())
    with pytest.raises(ValueError):
        inverse_vol_weights((0.1, 0.0))
    with pytest.raises(ValueError):
        equal_risk_contribution([])
    with pytest.raises(ValueError):
        equal_risk_contribution([[0.1, 0.0], [0.0]])
    with pytest.raises(ValueError):
        equal_risk_contribution([[0.04, 0.0], [0.0, 0.01]], budget=(1.0,))
    with pytest.raises(ValueError):
        equal_risk_contribution([[0.04, 0.0], [0.0, 0.01]], damp=0.0)
    with pytest.raises(ValueError):
        linear_granger_causality([1.0, 2.0], [1.0], lags=1)
    with pytest.raises(ValueError):
        coupled_ar_series(1)


def test_erc_weights_sum_and_positive_vol() -> None:
    cov = [[0.09, 0.01, 0.0], [0.01, 0.04, 0.0], [0.0, 0.0, 0.01]]
    res = equal_risk_contribution(cov)
    assert abs(sum(res.weights) - 1.0) < 1e-8
    assert all(w > 0 for w in res.weights)
    assert res.volatility > 0
    assert math.isclose(sum(res.budget), 1.0)
    assert math.isclose(sum(res.risk_fractions), 1.0)
