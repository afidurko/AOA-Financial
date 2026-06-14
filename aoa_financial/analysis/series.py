"""Pure-Python numeric primitives shared across the analysis modules.

These intentionally avoid numpy so the engine runs in a bare interpreter. If
numpy *is* installed it can be used by callers, but nothing here requires it.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from ..config import TRADING_DAYS_PER_YEAR


def log_returns(prices: Sequence[float]) -> List[float]:
    out = []
    for a, b in zip(prices, prices[1:]):
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


def simple_returns(prices: Sequence[float]) -> List[float]:
    return [(b / a - 1.0) for a, b in zip(prices, prices[1:]) if a > 0]


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def annualized_vol(returns: Sequence[float]) -> float:
    return stdev(returns) * math.sqrt(TRADING_DAYS_PER_YEAR)


def annualized_return(returns: Sequence[float]) -> float:
    """Geometric annualised return from a series of period log-returns."""
    if not returns:
        return 0.0
    total = sum(returns)  # sum of log returns = log of cumulative growth
    years = len(returns) / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return 0.0
    return math.exp(total / years) - 1.0


def sharpe(returns: Sequence[float], rf: float = 0.0) -> float:
    sd = stdev(returns)
    if sd == 0:
        return 0.0
    daily_rf = rf / TRADING_DAYS_PER_YEAR
    excess = mean(returns) - daily_rf
    return (excess / sd) * math.sqrt(TRADING_DAYS_PER_YEAR)


def max_drawdown(prices: Sequence[float]) -> float:
    """Largest peak-to-trough decline as a negative fraction."""
    peak = -math.inf
    mdd = 0.0
    for p in prices:
        peak = max(peak, p)
        if peak > 0:
            mdd = min(mdd, p / peak - 1.0)
    return mdd


def sma(xs: Sequence[float], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    s = 0.0
    from collections import deque
    q: deque = deque()
    for x in xs:
        q.append(x); s += x
        if len(q) > window:
            s -= q.popleft()
        out.append(s / window if len(q) == window else None)
    return out


def ema(xs: Sequence[float], window: int) -> List[Optional[float]]:
    if not xs:
        return []
    k = 2.0 / (window + 1.0)
    out: List[Optional[float]] = [None] * len(xs)
    prev: Optional[float] = None
    for i, x in enumerate(xs):
        if i + 1 < window:
            continue
        if prev is None:
            prev = sum(xs[i + 1 - window:i + 1]) / window  # seed with SMA
        else:
            prev = x * k + prev * (1 - k)
        out[i] = prev
    return out


def zscore(x: float, xs: Sequence[float]) -> float:
    sd = stdev(xs)
    return 0.0 if sd == 0 else (x - mean(xs)) / sd


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    xs, ys = xs[-n:], ys[-n:]
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return 0.0 if dx == 0 or dy == 0 else num / (dx * dy)


def ols(X: List[List[float]], y: List[float]) -> Tuple[List[float], float]:
    """Ordinary least squares via the normal equations (pure Python).

    ``X`` is a list of rows (each row a feature vector, intercept NOT added
    automatically). Returns ``(coefficients, r_squared)``. Solves
    ``(XᵀX) b = Xᵀy`` with Gaussian elimination + ridge fallback for
    near-singular systems.
    """
    n = len(X)
    if n == 0:
        return [], 0.0
    p = len(X[0])
    # Build XtX (p x p) and Xty (p).
    XtX = [[0.0] * p for _ in range(p)]
    Xty = [0.0] * p
    for i in range(n):
        xi = X[i]
        yi = y[i]
        for a in range(p):
            Xty[a] += xi[a] * yi
            for b in range(p):
                XtX[a][b] += xi[a] * xi[b]
    # Tiny ridge for numerical stability.
    for a in range(p):
        XtX[a][a] += 1e-8
    coef = _solve(XtX, Xty)
    # R^2.
    yhat = [sum(c * xij for c, xij in zip(coef, row)) for row in X]
    ybar = mean(y)
    ss_res = sum((yi - hi) ** 2 for yi, hi in zip(y, yhat))
    ss_tot = sum((yi - ybar) ** 2 for yi in y)
    r2 = 0.0 if ss_tot == 0 else max(0.0, 1.0 - ss_res / ss_tot)
    return coef, r2


def _solve(A: List[List[float]], b: List[float]) -> List[float]:
    """Gaussian elimination with partial pivoting."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            continue
        M[col], M[piv] = M[piv], M[col]
        pivval = M[col][col]
        for r in range(n):
            if r != col:
                factor = M[r][col] / pivval
                for k in range(col, n + 1):
                    M[r][k] -= factor * M[col][k]
    return [M[i][i] and M[i][n] / M[i][i] or 0.0 for i in range(n)]
