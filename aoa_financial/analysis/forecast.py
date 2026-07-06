"""Price forecasting.

Three complementary models are combined into an ensemble:

* **Drift-diffusion Monte Carlo** - simulates forward paths from the estimated
  drift and volatility, yielding a probabilistic cone (percentile bands).
* **Trend regression** - fits a linear trend on log-price and extrapolates.
* **EWMA mean-reversion** - exponentially weighted level as an anchor.

The ensemble blends their point estimates and reports an expected return,
direction, and a calibrated confidence derived from model agreement and the
width of the Monte-Carlo distribution.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from ..config import TRADING_DAYS_PER_YEAR
from . import series as S
from . import _backend as _b


@dataclass
class Forecast:
    horizon_days: int
    last_price: float
    expected_price: float
    expected_return: float
    direction: str                     # up | down | flat
    confidence: float                  # [0, 1]
    p10: float
    p50: float
    p90: float
    models: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "horizon_days": self.horizon_days, "last_price": self.last_price,
            "expected_price": round(self.expected_price, 4),
            "expected_return": round(self.expected_return, 4),
            "direction": self.direction, "confidence": round(self.confidence, 4),
            "p10": round(self.p10, 4), "p50": round(self.p50, 4),
            "p90": round(self.p90, 4),
            "models": {k: round(v, 4) for k, v in self.models.items()},
        }


def _trend_regression(closes: Sequence[float], horizon: int) -> float:
    logp = [math.log(c) for c in closes if c > 0]
    n = len(logp)
    if n < 10:
        return closes[-1]
    xs = list(range(n))
    # Simple linear fit on (x, log price).
    X = [[1.0, float(x)] for x in xs]
    coef, _ = S.ols(X, logp)
    pred_log = coef[0] + coef[1] * (n - 1 + horizon)
    return math.exp(pred_log)


def _ewma_anchor(closes: Sequence[float], span: int = 40) -> float:
    e = S.ema(closes, span)
    return next((x for x in reversed(e) if x is not None), closes[-1])


def _monte_carlo(closes: Sequence[float], horizon: int, sims: int = 2000,
                 seed: int = 7) -> Dict[str, float]:
    rets = S.log_returns(closes)
    look = rets[-min(len(rets), 504):]   # ~2y of daily returns
    mu = S.mean(look)
    sigma = S.stdev(look) or 1e-4
    last = closes[-1]
    if _b.HAS_NUMPY:
        # Vectorised: simulate every path at once (and afford more paths).
        finals = _b.monte_carlo_finals(last, mu, sigma, horizon,
                                       max(sims, 10000), seed)
    else:
        rng = random.Random(seed)
        finals = []
        for _ in range(sims):
            logp = math.log(last)
            for _ in range(horizon):
                logp += rng.gauss(mu, sigma)
            finals.append(math.exp(logp))
        finals.sort()

    def pct(p: float) -> float:
        idx = min(len(finals) - 1, max(0, int(p * len(finals))))
        return finals[idx]

    return {"p10": pct(0.10), "p50": pct(0.50), "p90": pct(0.90),
            "mean": S.mean(finals), "mu": mu, "sigma": sigma}


def forecast(closes: Sequence[float], horizon_days: int = 21,
             *, weights: Dict[str, float] | None = None) -> Forecast:
    if len(closes) < 30:
        last = closes[-1] if closes else 0.0
        return Forecast(horizon_days, last, last, 0.0, "flat", 0.2,
                        last, last, last, {})

    last = closes[-1]
    mc = _monte_carlo(closes, horizon_days)
    trend = _trend_regression(closes, horizon_days)
    anchor = _ewma_anchor(closes)
    # Mean-reversion expectation: drift part way from last toward the EWMA
    # anchor over the horizon.
    revert_speed = min(1.0, horizon_days / 60.0)
    ewma_pred = last + (anchor - last) * revert_speed

    models = {"monte_carlo": mc["mean"], "trend": trend, "ewma": ewma_pred}
    default_w = {"monte_carlo": 0.45, "trend": 0.35, "ewma": 0.20}
    w = weights or default_w
    total = sum(w.get(k, default_w.get(k, 0.0)) for k in models)
    if total <= 0:
        w = default_w
        total = sum(w.values())
    expected = sum(models[k] * w.get(k, 0.0) / total for k in models)
    exp_ret = expected / last - 1.0

    # Confidence: high when models agree and the MC cone is tight relative to
    # the move.
    spread = abs(models["trend"] - models["monte_carlo"]) / last
    cone = (mc["p90"] - mc["p10"]) / last
    agreement = max(0.0, 1.0 - spread * 4.0)
    tightness = max(0.0, 1.0 - cone * 1.5)
    confidence = max(0.05, min(0.95, 0.5 * agreement + 0.5 * tightness))

    direction = "up" if exp_ret > 0.005 else "down" if exp_ret < -0.005 else "flat"
    return Forecast(
        horizon_days=horizon_days, last_price=last, expected_price=expected,
        expected_return=exp_ret, direction=direction, confidence=confidence,
        p10=mc["p10"], p50=mc["p50"], p90=mc["p90"], models=models,
    )
