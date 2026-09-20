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
        inverse_vol_weights((float("nan"), 1.0))
    with pytest.raises(ValueError):
        inverse_vol_weights((float("inf"), 1.0))
    with pytest.raises(ValueError):
        inverse_vol_weights((1e-320, 1.0))
    with pytest.raises(ValueError):
        equal_risk_contribution([])
    with pytest.raises(ValueError):
        equal_risk_contribution([[0.1, 0.0], [0.0]])
    with pytest.raises(ValueError):
        equal_risk_contribution([[0.04, float("nan")], [0.0, 0.01]])
    with pytest.raises(ValueError):
        equal_risk_contribution([[0.04, 0.0], [0.0, 0.01]], budget=(1.0,))
    with pytest.raises(ValueError):
        equal_risk_contribution([[0.04, 0.0], [0.0, 0.01]], damp=0.0)
    with pytest.raises(ValueError):
        linear_granger_causality([1.0, 2.0], [1.0], lags=1)
    with pytest.raises(ValueError):
        coupled_ar_series(1)


def test_billion_stress_small_ok() -> None:
    from aoa.research.open_quant_patterns import billion_stress

    result = billion_stress(iterations=250_000, seed=3)
    assert result["ok"] is True
    assert result["inverse_vol_checks"] == 250_000
    assert result["erc_checks"] >= 3
    assert result["never_live"] is True


def test_trillion_stress_addons_ok() -> None:
    from aoa.research.open_quant_patterns import trillion_stress

    result = trillion_stress(iterations=250_000, seed=11, batch_size=50_000)
    assert result["ok"] is True
    assert result["inverse_vol_checks"] == 250_000
    assert result["tangency_checks"] >= 3
    assert result["hrp_checks"] >= 3
    assert result["stylized_checks"] >= 3
    assert result["network_checks"] >= 3
    assert result["never_live"] is True


def test_tangency_unconstrained_negative_excess() -> None:
    """All-negative excess returns must still yield finite weights summing to 1."""
    from aoa.research.open_quant_patterns import tangency_weights

    tan = tangency_weights(
        (-0.03, -0.02),
        [[0.04, 0.01], [0.01, 0.05]],
        long_only=False,
    )
    assert abs(sum(tan.weights) - 1.0) < 1e-8
    assert all(math.isfinite(w) for w in tan.weights)


def test_hrp_rejects_zero_diagonal() -> None:
    from aoa.research.open_quant_patterns import hierarchical_risk_parity

    with pytest.raises(ValueError, match="positive diagonal"):
        hierarchical_risk_parity([[0.0, 0.0], [0.0, 0.04]])


def test_tangency_and_hrp_sum_to_one() -> None:
    from aoa.research.open_quant_patterns import (
        hierarchical_risk_parity,
        tangency_weights,
    )

    cov = [[0.04, 0.01], [0.01, 0.02]]
    tan = tangency_weights((0.1, 0.08), cov, long_only=True)
    hrp = hierarchical_risk_parity(cov)
    assert abs(sum(tan.weights) - 1.0) < 1e-8
    assert abs(sum(hrp.weights) - 1.0) < 1e-8
    assert tan.volatility > 0
    assert hrp.volatility > 0


def test_stylized_facts_and_network() -> None:
    from aoa.research.open_quant_patterns import (
        correlation_network,
        log_returns,
        stylized_facts,
    )

    closes = [100.0]
    for i in range(40):
        closes.append(closes[-1] * (1.01 if i % 3 else 0.99))
    facts = stylized_facts(log_returns(closes))
    assert facts.n >= 30
    assert math.isfinite(facts.excess_kurtosis)
    net = correlation_network(
        [[1.0, 0.9, 0.0], [0.9, 1.0, 0.1], [0.0, 0.1, 1.0]],
        threshold=0.5,
    )
    assert len(net.edges) == 1
    assert net.degree[0] == 1


def test_compare_allocators_and_snapshot_context() -> None:
    from datetime import datetime, timezone

    from aoa.brokerage.models import Bar
    from aoa.data.market_data import SymbolSnapshot
    from aoa.research.open_quant_patterns import (
        compare_allocators,
        coupled_ar_series,
        snapshot_research_context,
    )

    x, _ = coupled_ar_series(80, seed=1, ar_x=0.4, coupling=0.0)
    y, _ = coupled_ar_series(80, seed=18, ar_x=0.3, coupling=0.0)
    z, _ = coupled_ar_series(80, seed=100, ar_x=0.25, coupling=0.0)
    cmp = compare_allocators([x, y, z])
    assert cmp["n_assets"] == 3
    assert abs(sum(cmp["tangency"]) - 1.0) < 1e-8
    assert abs(sum(cmp["cvar_budget"]) - 1.0) < 1e-8
    assert abs(sum(cmp["black_litterman"]) - 1.0) < 1e-8
    assert abs(sum(cmp["tangency_shrunk"]) - 1.0) < 1e-8
    assert 0.0 <= float(cmp["shrinkage"]) <= 1.0
    assert cmp["mst_edges"] == 2
    bars = [
        Bar(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i * 0.5,
            volume=1,
        )
        for i in range(60)
    ]
    ctx = snapshot_research_context(SymbolSnapshot(symbol="X", quote=None, bars=bars))
    assert ctx["available"] is True
    assert ctx["never_live"] is True
    assert "regime" in ctx


def test_mst_pmfg_partial_and_kde() -> None:
    from aoa.research.open_quant_patterns import (
        historical_cvar,
        kde_entropy,
        kde_mutual_information_stats,
        ledoit_wolf_cov,
        minimum_spanning_tree,
        partial_correlation_network,
        planar_maximally_filtered_graph,
        silverman_bandwidth,
        stylized_regime_summary,
    )

    corr = [
        [1.0, 0.9, 0.2, 0.1],
        [0.9, 1.0, 0.3, 0.15],
        [0.2, 0.3, 1.0, 0.8],
        [0.1, 0.15, 0.8, 1.0],
    ]
    mst = minimum_spanning_tree(corr)
    assert mst.kind == "mst"
    assert len(mst.edges) == 3
    pmfg = planar_maximally_filtered_graph(corr)
    assert pmfg.kind == "pmfg"
    assert len(pmfg.edges) == 3 * (4 - 2)
    cov = [[0.04, 0.01, 0.0], [0.01, 0.03, 0.005], [0.0, 0.005, 0.02]]
    partial = partial_correlation_network(cov, threshold=0.01)
    assert partial.kind == "partial"
    xs = [math.sin(i / 7) for i in range(80)]
    ys = [math.sin(i / 7 + 0.2) for i in range(80)]
    assert silverman_bandwidth(xs) > 0
    assert math.isfinite(kde_entropy(xs, grid_size=64))
    kde = kde_mutual_information_stats(xs, ys, grid_size=32)
    assert kde.bins == 0
    assert kde.mutual_information >= 0.0
    panel = [xs, ys, [math.cos(i / 9) for i in range(80)]]
    shrunk = ledoit_wolf_cov(panel)
    assert 0.0 <= shrunk.shrinkage <= 1.0
    assert len(shrunk.cov) == 3
    assert historical_cvar(xs, alpha=0.1) == historical_cvar(xs, alpha=0.1)
    regime = stylized_regime_summary(xs, window=40, step=10)
    assert regime.n_windows >= 1
    assert regime.regime in ("fat_tails", "vol_cluster", "calm", "mixed")


def test_black_litterman_and_cvar_budget() -> None:
    from aoa.research.open_quant_patterns import (
        black_litterman_weights,
        cvar_risk_budget_weights,
    )

    x, _ = coupled_ar_series(100, seed=2, ar_x=0.3, coupling=0.0)
    y, _ = coupled_ar_series(100, seed=5, ar_x=0.2, coupling=0.0)
    z, _ = coupled_ar_series(100, seed=9, ar_x=0.25, coupling=0.0)
    panel = [x, y, z]
    cov = cov_from_returns(panel)
    bl = black_litterman_weights(
        cov,
        [1 / 3, 1 / 3, 1 / 3],
        views_p=[[1.0, -0.5, -0.5]],
        views_q=[0.01],
        long_only=True,
    )
    assert abs(sum(bl.weights) - 1.0) < 1e-8
    assert all(w >= -1e-12 for w in bl.weights)
    cvar = cvar_risk_budget_weights(panel, alpha=0.1)
    assert abs(sum(cvar.weights) - 1.0) < 1e-8
    assert math.isfinite(cvar.cvar)


def test_erc_weights_sum_and_positive_vol() -> None:
    cov = [[0.09, 0.01, 0.0], [0.01, 0.04, 0.0], [0.0, 0.0, 0.01]]
    res = equal_risk_contribution(cov)
    assert abs(sum(res.weights) - 1.0) < 1e-8
    assert all(w > 0 for w in res.weights)
    assert res.volatility > 0
    assert math.isclose(sum(res.budget), 1.0)
    assert math.isclose(sum(res.risk_fractions), 1.0)
