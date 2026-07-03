"""Reverse-engineering market trends.

Given an observed price history, this model infers the latent forces that most
plausibly *generated* the trend and quantifies their relative influence. It is
the synthesis layer the brief asks for: "reverse engineer stock market trends
based on market analysis, sentiment, fundamentals and other factors ... make
inferences and assumptions to help understand current trends."

Method
------
1. Fit the linear factor model (momentum / reversal / trend / volatility /
   market) to explain next-day returns -> coefficient signs & magnitudes.
2. Reconstruct the return series from the fitted factors and measure how much
   of the variance is explained vs. left to idiosyncratic noise.
3. Decompose realised performance into a *trend (drift)* component and a
   *volatility (risk)* component.
4. Read the current regime and recent sentiment.
5. Emit explicit, human-readable **inferences** (what the data implies) and
   **assumptions** (what must hold for the read to be valid), plus a single
   forward-looking bias score in [-1, 1] for the swarm to consume.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..config import TRADING_DAYS_PER_YEAR
from ..databases.store import Bar
from . import series as S
from . import factors as F
from . import regimes as R


@dataclass
class ReverseEngineerResult:
    ticker: str
    explained_variance: float           # R^2 of factor reconstruction
    dominant_drivers: List[str]
    driver_shares: Dict[str, float]
    trend_component: float              # annualised drift
    risk_component: float               # annualised vol
    drift_to_risk: float                # trend / risk (a Sharpe-like read)
    regime: str
    regime_confidence: float
    sentiment: float
    forward_bias: float                 # [-1, 1] synthesised directional bias
    inferences: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    factor_model: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "explained_variance": round(self.explained_variance, 4),
            "dominant_drivers": self.dominant_drivers,
            "driver_shares": {k: round(v, 4) for k, v in self.driver_shares.items()},
            "trend_component": round(self.trend_component, 4),
            "risk_component": round(self.risk_component, 4),
            "drift_to_risk": round(self.drift_to_risk, 4),
            "regime": self.regime,
            "regime_confidence": round(self.regime_confidence, 4),
            "sentiment": round(self.sentiment, 4),
            "forward_bias": round(self.forward_bias, 4),
            "inferences": self.inferences,
            "assumptions": self.assumptions,
            "factor_model": self.factor_model,
        }


def reverse_engineer(
    ticker: str,
    bars: Sequence[Bar],
    *,
    benchmark: Optional[Sequence[float]] = None,
    stored_sentiment: Optional[float] = None,
) -> ReverseEngineerResult:
    closes = [b.close for b in bars]
    rets = S.log_returns(closes)

    # (1) Factor model.
    fm = F.fit(bars, benchmark)
    driver_shares = dict(fm.contributions)
    dominant = sorted(driver_shares, key=driver_shares.get, reverse=True)[:3]

    # (3) Trend vs risk decomposition.
    trend = S.annualized_return(rets)
    risk = S.annualized_vol(rets) or 1e-6
    drift_to_risk = trend / risk

    # (4) Regime + sentiment.
    regime_state = R.classify(bars)
    from . import sentiment as SENT
    sentiment = SENT.blended(stored_sentiment, rets[-21:])

    # (5) Synthesise a forward bias by combining the inferred forces. Each
    # component is bounded so no single one dominates.
    bias_terms = {
        "trend": math.tanh(2.0 * trend),
        "regime": _regime_bias(regime_state.regime) * regime_state.confidence,
        "sentiment": 0.5 * sentiment,
        "momentum_factor": _signed_factor(fm, "momentum"),
        "risk_penalty": -0.3 * max(0.0, risk - 0.4),  # punish very high vol
    }
    forward_bias = max(-1.0, min(1.0, sum(bias_terms.values()) / 2.2))

    inferences = _build_inferences(fm, trend, risk, drift_to_risk,
                                   regime_state, sentiment, dominant)
    assumptions = _build_assumptions(fm, regime_state)

    return ReverseEngineerResult(
        ticker=ticker,
        explained_variance=fm.r_squared,
        dominant_drivers=dominant,
        driver_shares=driver_shares,
        trend_component=trend,
        risk_component=risk,
        drift_to_risk=drift_to_risk,
        regime=regime_state.regime,
        regime_confidence=regime_state.confidence,
        sentiment=sentiment,
        forward_bias=forward_bias,
        inferences=inferences,
        assumptions=assumptions,
        factor_model=fm.to_dict(),
    )


def _regime_bias(regime: str) -> float:
    return {"bull": 0.8, "recovery": 0.5, "sideways": 0.0,
            "correction": -0.5, "bear": -0.8}.get(regime, 0.0)


def _signed_factor(fm: F.FactorModel, name: str) -> float:
    c = fm.coefficients.get(name, 0.0)
    return max(-0.5, min(0.5, c * 50.0))   # scale tiny daily coefs into range


def _build_inferences(fm, trend, risk, dr, regime, sentiment, dominant) -> List[str]:
    out: List[str] = []
    if dominant:
        out.append(
            f"Returns are driven primarily by {', '.join(dominant)} "
            f"(explained variance R²={fm.r_squared:.2f}).")
    if dr > 0.6:
        out.append(f"Strong risk-adjusted drift (trend/risk={dr:.2f}): the "
                   "uptrend is well compensated for its volatility.")
    elif dr < -0.4:
        out.append(f"Negative risk-adjusted drift (trend/risk={dr:.2f}): the "
                   "decline is structural, not just noise.")
    else:
        out.append(f"Weak risk-adjusted drift (trend/risk={dr:.2f}): trend is "
                   "fragile relative to volatility.")
    out.append(f"Current regime read as '{regime.regime}' "
               f"(confidence {regime.confidence:.0%}, "
               f"annualised vol {risk:.0%}).")
    if abs(sentiment) > 0.3:
        tone = "supportive" if sentiment > 0 else "adverse"
        out.append(f"Sentiment is {tone} ({sentiment:+.2f}), reinforcing the "
                   "near-term directional read.")
    mom = fm.coefficients.get("momentum", 0.0)
    if mom > 0:
        out.append("Positive momentum loading implies trend-following behaviour "
                   "(winners keep winning over the lookback).")
    elif mom < 0:
        out.append("Negative momentum loading implies mean-reverting behaviour "
                   "(extremes tend to snap back).")
    return out


def _build_assumptions(fm, regime) -> List[str]:
    return [
        "Past return-generating relationships (factor loadings) persist over the "
        "forecast horizon.",
        "No structural break (M&A, regulation, accounting restatement) occurs "
        "that invalidates the historical regime.",
        f"The '{regime.regime}' regime persists long enough for the inferred "
        "bias to play out; regime shifts would dominate the factor read.",
        "Liquidity remains sufficient that observed prices reflect fair value, "
        "not microstructure noise.",
    ]
