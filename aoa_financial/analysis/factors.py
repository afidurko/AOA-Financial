"""Factor engineering and a linear factor model.

Builds a panel of explanatory factors from the price series — momentum,
mean-reversion, trend, volatility, and (optionally) a market benchmark beta —
and fits a linear model of next-day returns on these factors. The fitted
coefficients quantify *which forces drive the stock's returns*, which is the
basis for the reverse-engineering layer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..databases.store import Bar
from . import series as S
from . import _backend as _b


@dataclass
class FactorModel:
    factors: List[str]
    coefficients: Dict[str, float]
    r_squared: float
    contributions: Dict[str, float]   # |coef * factor_stdev| normalised share

    def to_dict(self) -> dict:
        return {
            "factors": self.factors,
            "coefficients": {k: round(v, 6) for k, v in self.coefficients.items()},
            "r_squared": round(self.r_squared, 4),
            "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
        }


def _rolling(closes: Sequence[float], i: int, n: int) -> Optional[float]:
    if i - n < 0:
        return None
    return closes[i] / closes[i - n] - 1.0


def build_factor_panel(
    bars: Sequence[Bar],
    benchmark: Optional[Sequence[float]] = None,
) -> Dict[str, List[float]]:
    """Construct aligned factor columns and the target (next-day return)."""
    closes = [b.close for b in bars]

    # Fast path: vectorised rolling statistics when numpy is available. The
    # benchmark-only (non-market) columns are computed in one shot.
    if _b.HAS_NUMPY and benchmark is None:
        return _b.factor_columns(closes)

    rets = [0.0] + S.log_returns(closes)  # align length to closes
    n = len(closes)

    momentum: List[float] = []
    reversal: List[float] = []
    trend: List[float] = []
    vol: List[float] = []
    bench: List[float] = []
    target: List[float] = []

    # We need lookback of 60 and a next-day target, so iterate the valid range.
    for i in range(60, n - 1):
        mom = _rolling(closes, i, 60) or 0.0
        rev = -(_rolling(closes, i, 5) or 0.0)         # short-term reversal
        sma20 = S.mean(closes[i - 20:i]) or closes[i]
        tr = closes[i] / sma20 - 1.0
        window_rets = rets[i - 20:i]
        v = S.stdev(window_rets)
        momentum.append(mom)
        reversal.append(rev)
        trend.append(tr)
        vol.append(v)
        if benchmark is not None and i < len(benchmark):
            bench.append(benchmark[i])
        target.append(rets[i + 1])

    panel = {"momentum": momentum, "reversal": reversal,
             "trend": trend, "volatility": vol, "target": target}
    if bench and len(bench) == len(target):
        panel["market"] = bench
    return panel


def fit(bars: Sequence[Bar],
        benchmark: Optional[Sequence[float]] = None) -> FactorModel:
    panel = build_factor_panel(bars, benchmark)
    target = panel.pop("target")
    factor_names = list(panel.keys())
    if not target or not factor_names:
        return FactorModel([], {}, 0.0, {})

    # Standardise factors so coefficients are comparable in magnitude.
    standardized: Dict[str, List[float]] = {}
    stdevs: Dict[str, float] = {}
    for name in factor_names:
        col = panel[name]
        m = S.mean(col)
        sd = S.stdev(col) or 1.0
        stdevs[name] = sd
        standardized[name] = [(x - m) / sd for x in col]

    # Design matrix with intercept.
    rows = len(target)
    X = [[1.0] + [standardized[name][i] for name in factor_names]
         for i in range(rows)]
    coef, r2 = S.ols(X, target)
    coeffs = {"intercept": coef[0]}
    for name, c in zip(factor_names, coef[1:]):
        coeffs[name] = c

    # Contribution share = |coef| (factors already unit-variance) normalised.
    raw = {name: abs(coeffs[name]) for name in factor_names}
    total = sum(raw.values()) or 1.0
    contributions = {name: raw[name] / total for name in factor_names}

    return FactorModel(factor_names, coeffs, r2, contributions)
