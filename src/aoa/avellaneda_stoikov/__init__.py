"""Offline Avellaneda–Stoikov market-making research lane for AOA Financial.

Ports the simulation math from
`afidurko/avellaneda-stoikov <https://github.com/afidurko/avellaneda-stoikov>`_
into pure Python for offline research.

This package is intentionally **research-only** and separate from:

* live ``swarm`` / ``execution`` — never submit live orders from this path
* ``aoa.simulation`` — bar Monte-Carlo / scenario stress
* optional ``aoa.hftbacktest`` / ``aoa.orderbook`` tick lanes (sibling PRs)

Commands::

    aoa avellaneda status
    aoa avellaneda smoke
    aoa avellaneda simulate
"""

from __future__ import annotations

from aoa.avellaneda_stoikov.model import (
    ASParams,
    Quotes,
    arrival_intensity,
    fill_probability,
    limited_horizon_quotes,
    reservation_spread,
    unlimited_horizon_quotes,
)
from aoa.avellaneda_stoikov.probe import FORK_URL, probe_status

__all__ = [
    "ASParams",
    "FORK_URL",
    "Quotes",
    "SimResult",
    "SmokeResult",
    "arrival_intensity",
    "fill_probability",
    "limited_horizon_quotes",
    "probe_status",
    "reservation_spread",
    "run_ensemble",
    "run_simulation",
    "run_synthetic_smoke",
    "unlimited_horizon_quotes",
]


def __getattr__(name: str):
    if name in {"SimResult", "run_ensemble", "run_simulation"}:
        from aoa.avellaneda_stoikov.simulate import SimResult, run_ensemble, run_simulation

        return {
            "SimResult": SimResult,
            "run_ensemble": run_ensemble,
            "run_simulation": run_simulation,
        }[name]
    if name in {"SmokeResult", "run_synthetic_smoke"}:
        from aoa.avellaneda_stoikov.smoke import SmokeResult, run_synthetic_smoke

        return {"SmokeResult": SmokeResult, "run_synthetic_smoke": run_synthetic_smoke}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
