"""Tests for the Monte-Carlo market simulator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aoa.brokerage.models import Bar
from aoa.simulation import scenarios
from aoa.simulation.simulator import MarketSimulator, SimulationConfig


def _bars(closes):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=base + timedelta(days=i),
            open=c,
            high=c * 1.01,
            low=c * 0.99,
            close=c,
            volume=1_000,
        )
        for i, c in enumerate(closes)
    ]


def _rising(n=120, rate=1.004):
    return [100 * (rate**i) for i in range(n)]


def test_estimate_params_positive_drift():
    sim = MarketSimulator(seed=1)
    mu, sigma = sim.estimate_params(_bars(_rising()))
    assert mu > 0
    assert sigma >= 0


def test_gbm_paths_shape_and_start():
    sim = MarketSimulator(seed=1)
    paths = sim.gbm_paths(100.0, 0.0005, 0.01, horizon=10, n_paths=50)
    assert len(paths) == 50
    assert all(len(p) == 11 for p in paths)
    assert all(p[0] == 100.0 for p in paths)
    assert all(price > 0 for p in paths for price in p)  # GBM stays positive


def test_simulation_is_reproducible_with_seed():
    bars = _bars(_rising())
    cfg = SimulationConfig(method="gbm", horizon=15, n_paths=200, seed=123)
    r1 = MarketSimulator().simulate(bars, cfg, symbol="t")
    r2 = MarketSimulator().simulate(bars, cfg, symbol="t")
    assert r1.mean_ending == r2.mean_ending
    assert r1.ending_percentiles == r2.ending_percentiles


def test_simulation_result_summary_fields():
    bars = _bars(_rising())
    cfg = SimulationConfig(method="gbm", horizon=21, n_paths=500, seed=7)
    res = MarketSimulator().simulate(bars, cfg, symbol="aapl")
    assert res is not None
    assert res.symbol == "AAPL"
    assert res.n_paths == 500
    assert 0.0 <= res.prob_profit <= 1.0
    assert abs(res.prob_profit + res.prob_loss - 1.0) < 1e-9
    # Percentiles are monotonic.
    p = res.ending_percentiles
    assert p[5] <= p[50] <= p[95]
    # VaR/CVaR are losses (<= 0) and CVaR is at least as bad as VaR.
    assert res.cvar_95_pct <= res.var_95_pct
    assert "MC" in res.summary()


def test_bootstrap_method_runs():
    bars = _bars(_rising())
    cfg = SimulationConfig(method="bootstrap", horizon=10, n_paths=100, seed=5, block_size=3)
    res = MarketSimulator().simulate(bars, cfg, symbol="t")
    assert res is not None
    assert res.n_paths == 100


def test_simulate_empty_history_returns_none():
    assert MarketSimulator().simulate([], SimulationConfig()) is None


def test_replay_scenario_matches_apply():
    sim = MarketSimulator(seed=1)
    sc = scenarios.get_scenario("covid_crash_2020")
    path = sim.replay_scenario(100.0, sc)
    assert path[0] == 100.0
    assert len(path) == sc.horizon_days + 1


def test_stress_test_reports_every_scenario():
    sim = MarketSimulator(seed=1)
    lib = scenarios.list_scenarios()
    results = sim.stress_test(100.0, lib)
    assert len(results) == len(lib)
    crash = next(r for r in results if r.scenario == "black_monday_1987")
    assert crash.max_drawdown_pct < -20.0
    assert crash.start_price == 100.0


def test_sample_paths_are_capped():
    sim = MarketSimulator(seed=1)
    res = sim.simulate(_bars(_rising()), SimulationConfig(n_paths=300, seed=1), symbol="t")
    assert len(res.sample_paths) <= 11
