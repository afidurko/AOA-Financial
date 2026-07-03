"""Historical market-trend analysis.

Pure-Python (no numpy/pandas, consistent with :mod:`aoa.data.indicators`). Given
a history of :class:`~aoa.brokerage.models.Bar`, this characterizes *what already
happened*: the overall trend, its strength, the return distribution, the regime,
and every meaningful drawdown. That characterization is the raw material the
simulator (:mod:`aoa.simulation.simulator`) uses to recreate plausible futures.

Every function degrades gracefully on a thin history — returning ``None`` or an
empty analysis rather than raising — so callers never crash on a short series.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from aoa.brokerage.models import Bar

TRADING_DAYS = 252


# --------------------------------------------------------------------- returns
def simple_returns(closes: Sequence[float]) -> list[float]:
    """Period-over-period simple returns: ``c[i]/c[i-1] - 1``."""
    return [
        closes[i] / closes[i - 1] - 1
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]


def log_returns(closes: Sequence[float]) -> list[float]:
    """Continuously-compounded returns: ``ln(c[i]/c[i-1])``."""
    return [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
        if closes[i - 1] > 0 and closes[i] > 0
    ]


def linear_regression(values: Sequence[float]) -> tuple[float, float, float]:
    """Least-squares fit of ``values`` against their index 0..n-1.

    Returns ``(slope, intercept, r_squared)``. A flat or single-point series
    yields ``(0.0, mean, 0.0)``.
    """
    n = len(values)
    if n < 2:
        return 0.0, (values[0] if values else 0.0), 0.0
    xs = range(n)
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (values[x] - mean_y) for x in xs)
    if sxx == 0:
        return 0.0, mean_y, 0.0
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    syy = sum((y - mean_y) ** 2 for y in values)
    r_squared = (sxy * sxy) / (sxx * syy) if syy > 0 else 0.0
    return slope, intercept, round(r_squared, 4)


def _moments(values: Sequence[float]) -> tuple[float, float, float, float]:
    """Return ``(mean, std, skew, excess_kurtosis)`` (sample std)."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0, 0.0, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    std = var**0.5
    if std == 0:
        return mean, 0.0, 0.0, 0.0
    m3 = sum((v - mean) ** 3 for v in values) / n
    m4 = sum((v - mean) ** 4 for v in values) / n
    skew = m3 / (std**3)
    kurtosis = m4 / (std**4) - 3.0  # excess (0 == normal)
    return mean, std, skew, kurtosis


# ------------------------------------------------------------------- drawdowns
@dataclass(frozen=True)
class DrawdownEvent:
    """A peak-to-trough decline of at least the configured threshold."""

    peak_index: int
    trough_index: int
    recovery_index: int | None  # first bar back at/above the prior peak, if any
    peak_price: float
    trough_price: float
    depth_pct: float  # negative; e.g. -23.4 means a 23.4% decline
    length_bars: int  # peak → trough
    recovered: bool

    def to_dict(self) -> dict:
        return {
            "peak_index": self.peak_index,
            "trough_index": self.trough_index,
            "recovery_index": self.recovery_index,
            "peak_price": round(self.peak_price, 4),
            "trough_price": round(self.trough_price, 4),
            "depth_pct": self.depth_pct,
            "length_bars": self.length_bars,
            "recovered": self.recovered,
        }


def max_drawdown(closes: Sequence[float]) -> float:
    """Worst peak-to-trough decline over the series, as a negative percent."""
    if len(closes) < 2:
        return 0.0
    peak = closes[0]
    worst = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = c / peak - 1
            if dd < worst:
                worst = dd
    return round(worst * 100, 2)


def current_drawdown(closes: Sequence[float]) -> float:
    """How far below the running peak the latest close sits (negative percent)."""
    if not closes:
        return 0.0
    peak = max(closes)
    if peak <= 0:
        return 0.0
    return round((closes[-1] / peak - 1) * 100, 2)


def drawdown_events(closes: Sequence[float], threshold_pct: float = 10.0) -> list[DrawdownEvent]:
    """Identify every drawdown deeper than ``threshold_pct`` (a positive number).

    A new event starts at each fresh all-time-high peak; it closes when price
    recovers back to that peak (or at the end of the series, unrecovered).
    """
    if len(closes) < 2:
        return []
    thresh = abs(threshold_pct) / 100.0
    events: list[DrawdownEvent] = []
    peak = closes[0]
    peak_idx = 0
    trough = closes[0]
    trough_idx = 0
    in_dd = False
    for i, c in enumerate(closes):
        if c >= peak:
            # Recovered (or new high): close out any qualifying drawdown.
            if in_dd and (peak - trough) / peak >= thresh:
                events.append(
                    DrawdownEvent(
                        peak_index=peak_idx,
                        trough_index=trough_idx,
                        recovery_index=i,
                        peak_price=peak,
                        trough_price=trough,
                        depth_pct=round((trough / peak - 1) * 100, 2),
                        length_bars=trough_idx - peak_idx,
                        recovered=True,
                    )
                )
            peak = c
            peak_idx = i
            trough = c
            trough_idx = i
            in_dd = False
        else:
            in_dd = True
            if c < trough:
                trough = c
                trough_idx = i
    # Series ended while still under water — record if it qualifies.
    if in_dd and (peak - trough) / peak >= thresh:
        events.append(
            DrawdownEvent(
                peak_index=peak_idx,
                trough_index=trough_idx,
                recovery_index=None,
                peak_price=peak,
                trough_price=trough,
                depth_pct=round((trough / peak - 1) * 100, 2),
                length_bars=trough_idx - peak_idx,
                recovered=False,
            )
        )
    events.sort(key=lambda e: e.depth_pct)  # deepest first
    return events


# ----------------------------------------------------------------- statistics
@dataclass(frozen=True)
class ReturnStats:
    n: int
    mean_daily_pct: float
    std_daily_pct: float
    annualized_return_pct: float
    annualized_vol_pct: float
    skew: float
    excess_kurtosis: float
    best_day_pct: float
    worst_day_pct: float
    positive_day_ratio: float

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "mean_daily_pct": self.mean_daily_pct,
            "std_daily_pct": self.std_daily_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "annualized_vol_pct": self.annualized_vol_pct,
            "skew": self.skew,
            "excess_kurtosis": self.excess_kurtosis,
            "best_day_pct": self.best_day_pct,
            "worst_day_pct": self.worst_day_pct,
            "positive_day_ratio": self.positive_day_ratio,
        }


def return_stats(closes: Sequence[float]) -> ReturnStats:
    rets = simple_returns(closes)
    if not rets:
        return ReturnStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    mean, std, skew, kurt = _moments(rets)
    positives = sum(1 for r in rets if r > 0)
    return ReturnStats(
        n=len(rets),
        mean_daily_pct=round(mean * 100, 4),
        std_daily_pct=round(std * 100, 4),
        annualized_return_pct=round(mean * TRADING_DAYS * 100, 2),
        annualized_vol_pct=round(std * (TRADING_DAYS**0.5) * 100, 2),
        skew=round(skew, 4),
        excess_kurtosis=round(kurt, 4),
        best_day_pct=round(max(rets) * 100, 2),
        worst_day_pct=round(min(rets) * 100, 2),
        positive_day_ratio=round(positives / len(rets), 4),
    )


# --------------------------------------------------------------------- regimes
def classify_regime(cagr_pct: float, ann_vol_pct: float, max_dd_pct: float) -> str:
    """Label the prevailing regime from trend, volatility, and drawdown.

    Heuristic but deterministic — high vol or a deep drawdown dominates the
    directional read, mirroring how a desk would describe the tape.
    """
    high_vol = ann_vol_pct >= 35.0
    deep_dd = max_dd_pct <= -20.0
    if deep_dd and cagr_pct < 0:
        return "bear_volatile" if high_vol else "bear"
    if cagr_pct >= 15.0:
        return "bull_volatile" if high_vol else "bull"
    if cagr_pct <= -15.0:
        return "bear_volatile" if high_vol else "bear"
    if high_vol:
        return "choppy_volatile"
    return "sideways"


# --------------------------------------------------------------------- summary
@dataclass(frozen=True)
class TrendAnalysis:
    symbol: str
    n_bars: int
    start_price: float
    end_price: float
    total_return_pct: float
    cagr_pct: float
    trend: str  # "up" | "down" | "sideways"
    slope_pct_per_bar: float
    r_squared: float
    max_drawdown_pct: float
    current_drawdown_pct: float
    regime: str
    returns: ReturnStats
    drawdowns: list[DrawdownEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "n_bars": self.n_bars,
            "start_price": round(self.start_price, 4),
            "end_price": round(self.end_price, 4),
            "total_return_pct": self.total_return_pct,
            "cagr_pct": self.cagr_pct,
            "trend": self.trend,
            "slope_pct_per_bar": self.slope_pct_per_bar,
            "r_squared": self.r_squared,
            "max_drawdown_pct": self.max_drawdown_pct,
            "current_drawdown_pct": self.current_drawdown_pct,
            "regime": self.regime,
            "returns": self.returns.to_dict(),
            "drawdowns": [d.to_dict() for d in self.drawdowns],
        }


def analyze_trends(
    bars: Sequence[Bar],
    symbol: str = "",
    *,
    drawdown_threshold_pct: float = 10.0,
    bars_per_year: int = TRADING_DAYS,
) -> TrendAnalysis | None:
    """Characterize the historical trend embedded in a bar series.

    Returns ``None`` when there are too few bars (< 2) to say anything.
    """
    closes = [b.close for b in bars]
    if len(closes) < 2:
        return None

    start_price = closes[0]
    end_price = closes[-1]
    total_return = (end_price / start_price - 1) if start_price > 0 else 0.0

    years = max(len(closes) - 1, 1) / bars_per_year
    if start_price > 0 and end_price > 0 and years > 0:
        cagr = (end_price / start_price) ** (1 / years) - 1
    else:
        cagr = 0.0

    slope, _, r2 = linear_regression(closes)
    mean_price = sum(closes) / len(closes)
    slope_pct = (slope / mean_price * 100) if mean_price > 0 else 0.0

    max_dd = max_drawdown(closes)
    cur_dd = current_drawdown(closes)
    stats = return_stats(closes)
    regime = classify_regime(round(cagr * 100, 2), stats.annualized_vol_pct, max_dd)

    # Direction blends the regression slope with realized total return so a noisy
    # but clearly trending series is not mislabeled "sideways".
    if slope_pct > 0.02 and total_return > 0.02:
        trend = "up"
    elif slope_pct < -0.02 and total_return < -0.02:
        trend = "down"
    else:
        trend = "sideways"

    return TrendAnalysis(
        symbol=symbol.upper(),
        n_bars=len(closes),
        start_price=start_price,
        end_price=end_price,
        total_return_pct=round(total_return * 100, 2),
        cagr_pct=round(cagr * 100, 2),
        trend=trend,
        slope_pct_per_bar=round(slope_pct, 4),
        r_squared=r2,
        max_drawdown_pct=max_dd,
        current_drawdown_pct=cur_dd,
        regime=regime,
        returns=stats,
        drawdowns=drawdown_events(closes, drawdown_threshold_pct),
    )
