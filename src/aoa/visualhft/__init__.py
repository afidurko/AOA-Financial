"""Offline VisualHFT microstructure research lane for AOA Financial.

Ports key study formulas from the open-source Windows desktop app
`VisualHFT <https://github.com/afidurko/VisualHFT>`_ (fork of
visualHFT/VisualHFT) into pure Python for offline research.

This package is intentionally **research-only** and separate from:

* the VisualHFT WPF desktop host (Windows / .NET 10 — live L2 dashboard)
* ``aoa.hftbacktest`` — tick-level L2/L3 backtest engine (optional extra)
* ``aoa.simulation`` — bar Monte-Carlo / scenario stress
* live ``swarm`` / ``execution`` — never submit live orders from this path

Commands::

    aoa visualhft status
    aoa visualhft smoke
    aoa visualhft studies
"""

from __future__ import annotations

from aoa.visualhft.catalog import STUDY_CATALOG, list_studies
from aoa.visualhft.probe import FORK_URL, UPSTREAM_URL, probe_status

__all__ = [
    "FORK_URL",
    "STUDY_CATALOG",
    "UPSTREAM_URL",
    "SmokeResult",
    "list_studies",
    "probe_status",
    "run_synthetic_smoke",
]


def __getattr__(name: str):
    if name in {"SmokeResult", "run_synthetic_smoke"}:
        from aoa.visualhft.smoke import SmokeResult, run_synthetic_smoke

        return {"SmokeResult": SmokeResult, "run_synthetic_smoke": run_synthetic_smoke}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
