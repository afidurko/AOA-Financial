"""Technical-analysis indicators and a consolidated snapshot.

Every function takes a list of closes (or Bars) and returns plain numbers, so
the technical agent and the LLM analyst can consume them directly.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

from ..databases.store import Bar
from . import series as S


def rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    if len(closes) <= period:
        return None
    gains, losses = 0.0, 0.0
    # Seed with first `period` deltas.
    for a, b in zip(closes[:period + 1], closes[1:period + 1]):
        d = b - a
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    # Wilder smoothing over the rest.
    for a, b in zip(closes[period:-1], closes[period + 1:]):
        d = b - a
        avg_gain = (avg_gain * (period - 1) + max(d, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26,
         signal: int = 9) -> Dict[str, Optional[float]]:
    ef = S.ema(closes, fast)
    es = S.ema(closes, slow)
    line = [(a - b) if a is not None and b is not None else None
            for a, b in zip(ef, es)]
    clean = [x for x in line if x is not None]
    sig = S.ema(clean, signal)
    macd_line = clean[-1] if clean else None
    signal_line = next((x for x in reversed(sig) if x is not None), None)
    hist = (macd_line - signal_line) if macd_line is not None and signal_line is not None else None
    return {"macd": macd_line, "signal": signal_line, "histogram": hist}


def bollinger(closes: Sequence[float], window: int = 20,
              num_std: float = 2.0) -> Dict[str, Optional[float]]:
    if len(closes) < window:
        return {"upper": None, "middle": None, "lower": None, "pct_b": None}
    win = list(closes[-window:])
    mid = S.mean(win)
    sd = S.stdev(win)
    upper, lower = mid + num_std * sd, mid - num_std * sd
    last = closes[-1]
    pct_b = None if upper == lower else (last - lower) / (upper - lower)
    return {"upper": upper, "middle": mid, "lower": lower, "pct_b": pct_b}


def atr(bars: Sequence[Bar], period: int = 14) -> Optional[float]:
    if len(bars) <= period:
        return None
    trs: List[float] = []
    for prev, cur in zip(bars[:-1], bars[1:]):
        tr = max(cur.high - cur.low,
                 abs(cur.high - prev.close),
                 abs(cur.low - prev.close))
        trs.append(tr)
    # Wilder-smoothed ATR.
    atr_val = S.mean(trs[:period])
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


@dataclass
class TechnicalSnapshot:
    last_close: float
    sma_50: Optional[float]
    sma_200: Optional[float]
    golden_cross: Optional[bool]      # 50 above 200
    rsi_14: Optional[float]
    macd_hist: Optional[float]
    bollinger_pct_b: Optional[float]
    atr_14: Optional[float]
    mom_21d: Optional[float]
    mom_252d: Optional[float]
    annualized_vol: float
    max_drawdown: float

    def to_dict(self) -> dict:
        return asdict(self)


def snapshot(bars: Sequence[Bar]) -> TechnicalSnapshot:
    closes = [b.close for b in bars]
    sma50 = S.sma(closes, 50)[-1] if len(closes) >= 50 else None
    sma200 = S.sma(closes, 200)[-1] if len(closes) >= 200 else None
    golden = (sma50 > sma200) if sma50 is not None and sma200 is not None else None
    rets = S.log_returns(closes)

    def mom(n: int) -> Optional[float]:
        return (closes[-1] / closes[-n - 1] - 1.0) if len(closes) > n else None

    return TechnicalSnapshot(
        last_close=closes[-1],
        sma_50=sma50, sma_200=sma200, golden_cross=golden,
        rsi_14=rsi(closes), macd_hist=macd(closes)["histogram"],
        bollinger_pct_b=bollinger(closes)["pct_b"], atr_14=atr(bars),
        mom_21d=mom(21), mom_252d=mom(252),
        annualized_vol=S.annualized_vol(rets[-252:] if len(rets) >= 252 else rets),
        max_drawdown=S.max_drawdown(closes),
    )
