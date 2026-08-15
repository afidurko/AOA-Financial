"""Synthetic smoke runner for Avellaneda–Stoikov quotes + path (offline)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from aoa.avellaneda_stoikov.model import ASParams, limited_horizon_quotes, reservation_spread
from aoa.avellaneda_stoikov.simulate import SimConfig, run_ensemble, run_simulation


@dataclass(frozen=True)
class SmokeResult:
    """Outcome of ``run_synthetic_smoke``."""

    ok: bool
    reservation: float
    ask: float
    bid: float
    spread: float
    final_pnl: float
    mean_pnl: float
    n_steps: int
    n_sims: int
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_synthetic_smoke(
    *,
    n_steps: int = 200,
    n_sims: int = 20,
    seed: int = 1,
) -> SmokeResult:
    """Exercise AS formulas + a short ensemble; never contacts venues.

    Suitable for ``aoa avellaneda smoke``.
    """
    if n_steps < 1:
        raise ValueError("n_steps must be >= 1")
    if n_sims < 1:
        raise ValueError("n_sims must be >= 1")

    params = ASParams(gamma=0.1, sigma=2.0, k=1.5, T=1.0)
    quotes = limited_horizon_quotes(mid=100.0, inventory=0.0, t=0.0, params=params)
    expected_spread = reservation_spread(params.gamma, params.k)
    path = run_simulation(
        SimConfig(n_steps=n_steps, seed=seed, params=params, limit_horizon=True)
    )
    ensemble = run_ensemble(
        n_sims=n_sims, seed=seed, n_steps=n_steps, limit_horizon=True, params=params
    )

    ok = (
        quotes.ask > quotes.reservation > quotes.bid
        and abs(quotes.spread - expected_spread) < 1e-9
        and quotes.spread > 0.0
        and math.isfinite(path.final_pnl)
        and math.isfinite(ensemble["mean_pnl"])
        and path.n_steps == n_steps
    )
    return SmokeResult(
        ok=ok,
        reservation=quotes.reservation,
        ask=quotes.ask,
        bid=quotes.bid,
        spread=quotes.spread,
        final_pnl=path.final_pnl,
        mean_pnl=float(ensemble["mean_pnl"]),
        n_steps=n_steps,
        n_sims=n_sims,
        seed=seed,
    )
