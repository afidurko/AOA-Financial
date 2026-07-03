"""Numerical backend.

Provides numpy-accelerated implementations of the hot numeric primitives. When
numpy is installed these are used automatically; when it is not, the callers in
:mod:`series` fall back to their pure-Python equivalents. Either way the public
results are identical (within floating-point tolerance).

Design contract: every function here returns native Python ``list`` / ``float``
objects — never bare numpy arrays — so downstream code that does list
concatenation (``[0.0] + log_returns(...)``) and ``None``-aware slicing keeps
working unchanged regardless of backend.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

try:  # optional acceleration
    import numpy as _np
    HAS_NUMPY = True
except Exception:  # pragma: no cover - exercised only when numpy is absent
    _np = None
    HAS_NUMPY = False


def log_returns(prices: Sequence[float]) -> List[float]:
    a = _np.asarray(prices, dtype=float)
    if a.size < 2:
        return []
    prev, cur = a[:-1], a[1:]
    valid = (prev > 0) & (cur > 0)
    out = _np.log(cur[valid] / prev[valid])
    return out.tolist()


def simple_returns(prices: Sequence[float]) -> List[float]:
    a = _np.asarray(prices, dtype=float)
    if a.size < 2:
        return []
    prev, cur = a[:-1], a[1:]
    valid = prev > 0
    return (cur[valid] / prev[valid] - 1.0).tolist()


def stdev(xs: Sequence[float]) -> float:
    a = _np.asarray(xs, dtype=float)
    if a.size < 2:
        return 0.0
    # Sample standard deviation (ddof=1) to match the pure-Python version.
    return float(a.std(ddof=1))


def sma(xs: Sequence[float], window: int) -> List[Optional[float]]:
    a = _np.asarray(xs, dtype=float)
    n = a.size
    out: List[Optional[float]] = [None] * n
    if n < window or window <= 0:
        return out
    csum = _np.cumsum(a)
    # rolling sum: csum[i] - csum[i-window]
    roll = csum[window - 1:].copy()
    roll[1:] -= csum[:-window]
    means = roll / window
    for i, m in enumerate(means):
        out[window - 1 + i] = float(m)
    return out


def ema(xs: Sequence[float], window: int) -> List[Optional[float]]:
    a = _np.asarray(xs, dtype=float)
    n = a.size
    out: List[Optional[float]] = [None] * n
    if n < window or window <= 0:
        return out
    k = 2.0 / (window + 1.0)
    prev = float(a[:window].mean())  # seed with SMA, matching pure version
    out[window - 1] = prev
    for i in range(window, n):
        prev = float(a[i]) * k + prev * (1.0 - k)
        out[i] = prev
    return out


def ols(X: List[List[float]], y: List[float]) -> Tuple[List[float], float]:
    """Least squares via numpy ``lstsq`` (SVD-based, robust to rank defects)."""
    Xm = _np.asarray(X, dtype=float)
    yv = _np.asarray(y, dtype=float)
    if Xm.size == 0:
        return [], 0.0
    coef, *_ = _np.linalg.lstsq(Xm, yv, rcond=None)
    yhat = Xm @ coef
    ss_res = float(((yv - yhat) ** 2).sum())
    ss_tot = float(((yv - yv.mean()) ** 2).sum())
    r2 = 0.0 if ss_tot == 0 else max(0.0, 1.0 - ss_res / ss_tot)
    return coef.tolist(), r2


def factor_columns(closes: Sequence[float]) -> dict:
    """Vectorised construction of the factor panel.

    Produces the same columns and index alignment as the pure-Python
    ``factors.build_factor_panel`` (rows for ``i`` in ``[60, n-2]``), but with
    rolling statistics computed as array operations instead of per-index
    Python loops over tiny slices.
    """
    C = _np.asarray(closes, dtype=float)
    n = C.size
    if n < 62:
        return {"momentum": [], "reversal": [], "trend": [],
                "volatility": [], "target": []}

    R = _np.empty(n)
    R[0] = 0.0
    R[1:] = _np.diff(_np.log(C))

    idx = _np.arange(60, n - 1)            # rows we emit

    # Rolling mean of the 20 closes *before* i  -> slice [i-20, i-1].
    prefixC = _np.concatenate(([0.0], _np.cumsum(C)))
    sma20 = (prefixC[idx] - prefixC[idx - 20]) / 20.0

    # Rolling sample std (ddof=1) of the 20 returns before i.
    prefixR = _np.concatenate(([0.0], _np.cumsum(R)))
    prefixR2 = _np.concatenate(([0.0], _np.cumsum(R * R)))
    s1 = prefixR[idx] - prefixR[idx - 20]
    s2 = prefixR2[idx] - prefixR2[idx - 20]
    var = (s2 - (s1 * s1) / 20.0) / 19.0
    vol = _np.sqrt(_np.clip(var, 0.0, None))

    momentum = C[idx] / C[idx - 60] - 1.0
    reversal = -(C[idx] / C[idx - 5] - 1.0)
    trend = C[idx] / sma20 - 1.0
    target = R[idx + 1]

    return {
        "momentum": momentum.tolist(), "reversal": reversal.tolist(),
        "trend": trend.tolist(), "volatility": vol.tolist(),
        "target": target.tolist(),
    }


def monte_carlo_finals(last: float, mu: float, sigma: float,
                       horizon: int, sims: int, seed: int) -> List[float]:
    """Vectorised terminal-price distribution for the forecast Monte Carlo.

    Simulates ``sims`` paths of ``horizon`` daily log-return steps at once and
    returns the sorted terminal prices.
    """
    rng = _np.random.default_rng(seed)
    shocks = rng.normal(mu, sigma, size=(sims, horizon))
    log_finals = math.log(last) + shocks.sum(axis=1)
    finals = _np.exp(log_finals)
    finals.sort()
    return finals.tolist()
