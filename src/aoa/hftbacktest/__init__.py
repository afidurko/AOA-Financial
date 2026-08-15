"""Optional HFT / market-making backtest lane via ``hftbacktest``.

This package wraps the open-source
`hftbacktest <https://github.com/afidurko/hftbacktest>`_ engine (fork of
nkaz001/hftbacktest) for tick-level L2/L3 replay with feed/order latency and
queue-position fill models.

It is intentionally **offline-only** and separate from:

* ``aoa.simulation`` — bar-level Monte-Carlo / scenario stress
* ``aoa_financial.backtest`` — daily walk-forward decision harness
* live ``swarm`` / ``execution`` — never submit live orders from this path

Install::

    pip install -e ".[hftbacktest]"

Then::

    aoa hft status
    aoa hft smoke
"""

from __future__ import annotations

try:
    import hftbacktest as _hftbacktest  # noqa: F401

    HAS_HFTBACKTEST = True
except ImportError:  # pragma: no cover - exercised when extra absent
    HAS_HFTBACKTEST = False

from aoa.hftbacktest.probe import probe_status

__all__ = [
    "HAS_HFTBACKTEST",
    "SmokeResult",
    "probe_status",
    "run_npz_smoke",
]


def __getattr__(name: str):
    """Lazy-load runners so ``import aoa.hftbacktest`` works without NumPy."""
    if name in {"SmokeResult", "run_npz_smoke"}:
        from aoa.hftbacktest.runner import SmokeResult, run_npz_smoke

        return {"SmokeResult": SmokeResult, "run_npz_smoke": run_npz_smoke}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
