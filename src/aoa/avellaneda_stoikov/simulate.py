"""Offline Avellaneda–Stoikov Monte-Carlo path (no matplotlib / broker)."""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from aoa.avellaneda_stoikov.model import (
    ASParams,
    arrival_intensity,
    fill_probability,
    intensity_scale,
    limited_horizon_quotes,
    unlimited_horizon_quotes,
)


@dataclass(frozen=True)
class SimConfig:
    """Discrete-time AS simulation settings."""

    n_steps: int = 200
    s0: float = 100.0
    drift_per_step: float = 0.0
    limit_horizon: bool = True
    params: ASParams = field(default_factory=ASParams)
    seed: int = 1


@dataclass(frozen=True)
class SimResult:
    """One simulated market-making path."""

    final_pnl: float
    final_inventory: float
    final_cash: float
    final_mid: float
    max_inventory: float
    min_inventory: float
    n_steps: int
    seed: int
    limit_horizon: bool
    gamma: float
    k: float
    sigma: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _brownian_path(s0: float, n: int, dt: float, sigma: float, rng: random.Random) -> list[float]:
    """Wiener increments with volatility ``sigma`` (absolute price units)."""
    path = [s0]
    scale = sigma * math.sqrt(dt)
    for _ in range(n):
        path.append(path[-1] + rng.gauss(0.0, scale))
    return path


def run_simulation(cfg: SimConfig | None = None) -> SimResult:
    """Run one AS market-making path; never contacts venues or brokers."""
    cfg = cfg or SimConfig()
    if cfg.n_steps < 1:
        raise ValueError("n_steps must be >= 1")

    params = cfg.params
    dt = params.T / cfg.n_steps
    rng = random.Random(cfg.seed)
    mids = _brownian_path(cfg.s0, cfg.n_steps, dt, params.sigma, rng)

    m = params.M if params.M is not None else cfg.s0 / 200.0
    A = params.A if params.A is not None else intensity_scale(dt, params.k, m)

    cash = 0.0
    inv = 0.0
    max_q = 0.0
    min_q = 0.0
    pnl = 0.0
    mid = cfg.s0

    for n in range(cfg.n_steps + 1):
        mid = mids[n] + cfg.drift_per_step * n
        t = dt * n
        if cfg.limit_horizon:
            quotes = limited_horizon_quotes(mid, inv, t, params)
        else:
            quotes = unlimited_horizon_quotes(mid, inv, params)

        lam_a = arrival_intensity(A, params.k, quotes.delta_ask)
        lam_b = arrival_intensity(A, params.k, quotes.delta_bid)
        d_na = 1 if rng.random() < fill_probability(lam_a, dt) else 0
        d_nb = 1 if rng.random() < fill_probability(lam_b, dt) else 0

        inv = inv - d_na + d_nb
        cash = cash + quotes.ask * d_na - quotes.bid * d_nb
        pnl = cash + inv * mid
        max_q = max(max_q, inv)
        min_q = min(min_q, inv)

    return SimResult(
        final_pnl=pnl,
        final_inventory=inv,
        final_cash=cash,
        final_mid=mid,
        max_inventory=max_q,
        min_inventory=min_q,
        n_steps=cfg.n_steps,
        seed=cfg.seed,
        limit_horizon=cfg.limit_horizon,
        gamma=params.gamma,
        k=params.k,
        sigma=params.sigma,
    )


def run_ensemble(
    *,
    n_sims: int = 50,
    seed: int = 1,
    n_steps: int = 200,
    limit_horizon: bool = True,
    params: ASParams | None = None,
) -> dict[str, Any]:
    """Average PnL over ``n_sims`` independent seeds (seed, seed+1, …)."""
    if n_sims < 1:
        raise ValueError("n_sims must be >= 1")
    params = params or ASParams()
    pnls: list[float] = []
    for i in range(n_sims):
        result = run_simulation(
            SimConfig(
                n_steps=n_steps,
                seed=seed + i,
                limit_horizon=limit_horizon,
                params=params,
            )
        )
        pnls.append(result.final_pnl)
    mean = sum(pnls) / n_sims
    var = sum((p - mean) ** 2 for p in pnls) / n_sims
    return {
        "n_sims": n_sims,
        "mean_pnl": mean,
        "std_pnl": math.sqrt(var),
        "min_pnl": min(pnls),
        "max_pnl": max(pnls),
        "seed": seed,
        "n_steps": n_steps,
        "limit_horizon": limit_horizon,
        "offline_only": True,
        "never_live": True,
    }
