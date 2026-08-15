"""Tests for Avellaneda–Stoikov research lane (offline, no broker)."""

from __future__ import annotations

import math

import pytest

from aoa.avellaneda_stoikov import (
    ASParams,
    limited_horizon_quotes,
    probe_status,
    reservation_spread,
    run_ensemble,
    run_simulation,
    run_synthetic_smoke,
    unlimited_horizon_quotes,
)
from aoa.avellaneda_stoikov.model import arrival_intensity, fill_probability
from aoa.avellaneda_stoikov.simulate import SimConfig


def test_reservation_spread_and_flat_inventory_quotes():
    gamma, k = 0.1, 1.5
    spread = reservation_spread(gamma, k)
    assert spread == pytest.approx((2.0 / gamma) * math.log(1.0 + gamma / k))
    params = ASParams(gamma=gamma, sigma=2.0, k=k, T=1.0)
    q = limited_horizon_quotes(100.0, inventory=0.0, t=0.0, params=params)
    assert q.reservation == pytest.approx(100.0)
    assert q.ask == pytest.approx(100.0 + spread / 2.0)
    assert q.bid == pytest.approx(100.0 - spread / 2.0)
    assert q.ask > q.bid


def test_long_inventory_skews_reservation_down():
    params = ASParams(gamma=0.1, sigma=2.0, k=1.5, T=1.0)
    flat = limited_horizon_quotes(100.0, 0.0, 0.0, params)
    long = limited_horizon_quotes(100.0, 5.0, 0.0, params)
    assert long.reservation < flat.reservation
    assert long.ask < flat.ask
    assert long.bid < flat.bid


def test_unlimited_horizon_and_intensity():
    params = ASParams(gamma=0.1, sigma=2.0, k=1.5, q_max=10.0)
    q = unlimited_horizon_quotes(100.0, inventory=0.0, params=params)
    assert q.ask > q.reservation > q.bid
    lam = arrival_intensity(A=10.0, k=1.5, delta=0.5)
    assert lam == pytest.approx(10.0 * math.exp(-1.5 * 0.5))
    assert fill_probability(0.0, 0.01) == pytest.approx(0.0)
    assert 0.0 < fill_probability(5.0, 0.01) < 1.0


def test_simulation_deterministic_and_ensemble():
    cfg = SimConfig(n_steps=50, seed=7, params=ASParams())
    a = run_simulation(cfg)
    b = run_simulation(cfg)
    assert a.to_dict() == b.to_dict()
    ens = run_ensemble(n_sims=5, seed=7, n_steps=50)
    assert ens["n_sims"] == 5
    assert math.isfinite(ens["mean_pnl"])
    assert ens["offline_only"] is True


def test_smoke_and_probe():
    status = probe_status()
    assert status["available"] is True
    assert status["never_live"] is True
    assert "avellaneda-stoikov" in status["fork"]
    result = run_synthetic_smoke(n_steps=40, n_sims=5, seed=1)
    assert result.ok
    assert result.ask > result.bid
    assert result.n_steps == 40


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        reservation_spread(0.0, 1.5)
    with pytest.raises(ValueError):
        run_simulation(SimConfig(n_steps=0))
    with pytest.raises(ValueError):
        run_synthetic_smoke(n_sims=0)
