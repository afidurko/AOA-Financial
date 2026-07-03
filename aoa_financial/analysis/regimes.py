"""Market-regime inference.

Classifies the *current* regime of a price series into one of five states by
reading trend strength and realised-volatility relative to the asset's own
history. This is the practical, explainable counterpart to a hidden-Markov
model: each state has clear, inspectable criteria, and a confidence is derived
from how decisively the criteria are met.

It also exposes ``regime_history`` for back-testing how regimes evolved, which
the reverse-engineering model consumes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ..config import TRADING_DAYS_PER_YEAR
from ..databases.store import Bar
from . import series as S

REGIMES = ("bull", "recovery", "sideways", "correction", "bear")


@dataclass
class RegimeState:
    regime: str
    confidence: float
    annualized_vol: float
    trend_strength: float      # slope of log-price per year (approx CAGR)
    drawdown: float

    def to_dict(self) -> dict:
        return {
            "regime": self.regime, "confidence": round(self.confidence, 4),
            "annualized_vol": round(self.annualized_vol, 4),
            "trend_strength": round(self.trend_strength, 4),
            "drawdown": round(self.drawdown, 4),
        }


def _trend_strength(closes: Sequence[float]) -> float:
    logp = [math.log(c) for c in closes if c > 0]
    n = len(logp)
    if n < 5:
        return 0.0
    xs = [[1.0, float(i)] for i in range(n)]
    coef, _ = S.ols(xs, logp)
    # slope per day -> annualised continuous growth.
    return coef[1] * TRADING_DAYS_PER_YEAR


def classify(bars: Sequence[Bar], window: int = 126) -> RegimeState:
    """Classify the regime over the trailing ``window`` trading days."""
    win = bars[-window:] if len(bars) > window else bars
    closes = [b.close for b in win]
    rets = S.log_returns(closes)
    vol = S.annualized_vol(rets)
    trend = _trend_strength(closes)
    dd = S.max_drawdown(closes)

    # Volatility relative to the asset's long history for normalisation.
    long_rets = S.log_returns([b.close for b in bars])
    long_vol = S.annualized_vol(long_rets) or vol or 0.2
    vol_ratio = vol / long_vol if long_vol else 1.0

    # Decision logic with graded confidence.
    if trend > 0.12 and dd > -0.15:
        regime = "bull"
        conf = min(0.95, 0.5 + trend)
    elif trend > 0.05 and dd < -0.12:
        regime = "recovery"
        conf = 0.55 + min(0.3, abs(dd))
    elif trend < -0.12 or dd < -0.30:
        regime = "bear"
        conf = min(0.95, 0.5 + abs(trend) + max(0.0, -dd - 0.3))
    elif trend < -0.04 or (dd < -0.10 and vol_ratio > 1.2):
        regime = "correction"
        conf = 0.5 + min(0.3, vol_ratio - 1.0)
    else:
        regime = "sideways"
        conf = 0.5 + max(0.0, 0.3 - abs(trend))

    return RegimeState(regime=regime, confidence=max(0.05, min(0.99, conf)),
                       annualized_vol=vol, trend_strength=trend, drawdown=dd)


def regime_history(bars: Sequence[Bar], window: int = 126,
                   step: int = 21) -> List[Tuple[str, RegimeState]]:
    """Return (date, RegimeState) samples stepping through history.

    Used to study regime transitions over the full life of the series.
    """
    out: List[Tuple[str, RegimeState]] = []
    n = len(bars)
    if n < window:
        return out
    for end in range(window, n + 1, step):
        seg = bars[:end]
        out.append((bars[end - 1].date, classify(seg, window=window)))
    return out
