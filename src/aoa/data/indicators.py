"""Pure-Python technical indicators.

No numpy/pandas dependency — these operate on plain ``list[float]`` and on lists
of :class:`~aoa.brokerage.models.Bar`. Every function returns ``None`` (or a
dict of ``None`` values) when there is insufficient data, so callers never crash
on a thin price history.

:func:`technical_snapshot` is the hot path (every symbol × every timeframe, every
cycle). It computes each intermediate series once and shares it between
indicators instead of letting ``ema``, ``macd``, ``sma`` and ``bollinger`` each
re-walk the closes.
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
    one_minus_k = 1 - k
    # Seed with the SMA of the first `period` values.
    prev = sum(values[:period]) / period
    out = [prev]
    append = out.append
    for v in values[period:]:
        prev = v * k + prev * one_minus_k
        append(prev)
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
    decay = period - 1
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            avg_gain = (avg_gain * decay + delta) / period
            avg_loss = (avg_loss * decay) / period
        else:
            avg_gain = (avg_gain * decay) / period
            avg_loss = (avg_loss * decay - delta) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _macd_from_series(
    fast_series: list[float],
    slow_series: list[float],
    signal: int,
) -> dict[str, float | None]:
    """MACD from precomputed fast/slow EMA series (shared with the snapshot)."""
    if not fast_series or not slow_series:
        return {"macd": None, "signal": None, "histogram": None}
    # Align the two EMA series to the same (shorter) tail length.
    n = min(len(fast_series), len(slow_series))
    fast_tail = fast_series[-n:]
    slow_tail = slow_series[-n:]
    macd_line = [f - s for f, s in zip(fast_tail, slow_tail, strict=True)]
    signal_series = ema_series(macd_line, signal)
    macd_val = macd_line[-1]
    if not signal_series:
        return {"macd": round(macd_val, 4), "signal": None, "histogram": None}
    signal_val = signal_series[-1]
    return {
        "macd": round(macd_val, 4),
        "signal": round(signal_val, 4),
        "histogram": round(macd_val - signal_val, 4),
    }


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, float | None]:
    """Return MACD line, signal line, and histogram."""
    if len(values) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}
    return _macd_from_series(ema_series(values, fast), ema_series(values, slow), signal)


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
    prev_close = bars[0].close
    trs: list[float] = []
    for bar in bars[1:]:
        high, low = bar.high, bar.low
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        prev_close = bar.close
    atr_val = sum(trs[:period]) / period
    decay = period - 1
    for tr in trs[period:]:
        atr_val = (atr_val * decay + tr) / period
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


def volume_metrics(bars: Sequence[Bar], window: int = 20) -> dict[str, float | None]:
    """Latest bar volume vs a trailing average (unusual-activity signal)."""
    if not bars:
        return {"latest_volume": None, "avg_volume_20d": None, "volume_ratio": None}
    tail = bars[-window:]
    latest = bars[-1].volume
    avg = sum(b.volume for b in tail) / len(tail)
    ratio = round(latest / avg, 2) if avg > 0 else None
    return {
        "latest_volume": round(latest, 0),
        "avg_volume_20d": round(avg, 0),
        "volume_ratio": ratio,
    }


def technical_snapshot(bars: Sequence[Bar]) -> dict:
    """Compute a compact dict of indicators from a bar history.

    This is the structured "technical context" handed to the LLM agents. The
    12/26 EMA series feed both the ``ema_*`` fields and MACD; the 20-bar window
    feeds both ``sma_20`` and the Bollinger middle band.
    """
    closes = [b.close for b in bars]
    n = len(closes)
    last = closes[-1] if closes else None

    fast_series = ema_series(closes, 12)
    slow_series = ema_series(closes, 26)
    if n >= 26 + 9:
        macd_val = _macd_from_series(fast_series, slow_series, 9)
    else:
        macd_val = {"macd": None, "signal": None, "histogram": None}

    bb = bollinger_bands(closes, 20)
    return {
        "last_close": last,
        "sma_20": bb["middle"],
        "sma_50": sma(closes, 50),
        "sma_200": sma(closes, 200),
        "ema_12": round(fast_series[-1], 4) if fast_series else None,
        "ema_26": round(slow_series[-1], 4) if slow_series else None,
        "rsi_14": rsi(closes, 14),
        "macd": macd_val,
        "bollinger": bb,
        "atr_14": atr(bars, 14),
        "realized_vol_20d": realized_volatility(closes),
        "return_5d_pct": pct_change(closes, 5),
        "return_20d_pct": pct_change(closes, 20),
        "volume": volume_metrics(bars),
        "n_bars": n,
    }
