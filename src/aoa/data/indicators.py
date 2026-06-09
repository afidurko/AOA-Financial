"""Pure-Python technical indicators.

No numpy/pandas dependency — these operate on plain ``list[float]`` and on lists
of :class:`~aoa.brokerage.models.Bar`. Every function returns ``None`` (or a
dict of ``None`` values) when there is insufficient data, so callers never crash
on a thin price history.
"""

from __future__ import annotations

from collections.abc import Sequence

from aoa.brokerage.models import Bar


def sma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 4)


def ema_series(values: Sequence[float], period: int) -> list[float]:
    """Full EMA series (same length as a usable tail). Empty if too short."""
    if period <= 0 or len(values) < period:
        return []
    k = 2 / (period + 1)
    # Seed with the SMA of the first `period` values.
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema(values: Sequence[float], period: int) -> float | None:
    series = ema_series(values, period)
    return round(series[-1], 4) if series else None


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    """Wilder's RSI."""
    if len(values) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, float | None]:
    """Return MACD line, signal line, and histogram."""
    if len(values) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}
    fast_series = ema_series(values, fast)
    slow_series = ema_series(values, slow)
    # Align the two EMA series to the same (shorter) tail length.
    n = min(len(fast_series), len(slow_series))
    macd_line = [fast_series[-n + i] - slow_series[-n + i] for i in range(n)]
    signal_series = ema_series(macd_line, signal)
    if not signal_series:
        return {"macd": round(macd_line[-1], 4), "signal": None, "histogram": None}
    macd_val = macd_line[-1]
    signal_val = signal_series[-1]
    return {
        "macd": round(macd_val, 4),
        "signal": round(signal_val, 4),
        "histogram": round(macd_val - signal_val, 4),
    }


def bollinger_bands(
    values: Sequence[float], period: int = 20, num_std: float = 2.0
) -> dict[str, float | None]:
    if len(values) < period:
        return {"upper": None, "middle": None, "lower": None}
    window = values[-period:]
    mid = sum(window) / period
    variance = sum((v - mid) ** 2 for v in window) / period
    std = variance**0.5
    return {
        "upper": round(mid + num_std * std, 4),
        "middle": round(mid, 4),
        "lower": round(mid - num_std * std, 4),
    }


def atr(bars: Sequence[Bar], period: int = 14) -> float | None:
    """Average True Range — a volatility measure for position sizing/stops."""
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        high, low = bars[i].high, bars[i].low
        prev_close = bars[i - 1].close
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if len(trs) < period:
        return None
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return round(atr_val, 4)


def realized_volatility(values: Sequence[float], window: int = 20) -> float | None:
    """Annualized realized volatility from daily closes (252 trading days)."""
    if len(values) < window + 1:
        return None
    rets = [
        (values[i] / values[i - 1]) - 1
        for i in range(len(values) - window, len(values))
        if values[i - 1] > 0
    ]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round((var**0.5) * (252**0.5), 4)


def pct_change(values: Sequence[float], lookback: int) -> float | None:
    if len(values) < lookback + 1 or values[-lookback - 1] == 0:
        return None
    return round((values[-1] / values[-lookback - 1] - 1) * 100, 2)


def technical_snapshot(bars: Sequence[Bar]) -> dict:
    """Compute a compact dict of indicators from a bar history.

    This is the structured "technical context" handed to the LLM agents.
    """
    closes = [b.close for b in bars]
    last = closes[-1] if closes else None
    bb = bollinger_bands(closes)
    return {
        "last_close": last,
        "sma_20": sma(closes, 20),
        "sma_50": sma(closes, 50),
        "sma_200": sma(closes, 200),
        "ema_12": ema(closes, 12),
        "ema_26": ema(closes, 26),
        "rsi_14": rsi(closes, 14),
        "macd": macd(closes),
        "bollinger": bb,
        "atr_14": atr(bars, 14),
        "realized_vol_20d": realized_volatility(closes),
        "return_5d_pct": pct_change(closes, 5),
        "return_20d_pct": pct_change(closes, 20),
        "n_bars": len(bars),
    }
