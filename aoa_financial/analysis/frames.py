"""Pandas DataFrame layer (optional).

This module is the tabular front-end to the engine. It is **only imported on
demand** (the stdlib core never depends on it), and importing it raises a clear
error if pandas is missing. It provides:

* IO between the SQLite store and ``pandas.DataFrame`` (and CSV).
* A one-pass **vectorised indicator suite** computing the full technical panel
  (SMA/EMA/RSI/MACD/Bollinger/ATR/returns/vol/drawdown) as DataFrame columns —
  the column-wise equivalent of :mod:`analysis.technical`, kept in parity with
  it by the test-suite.
* Cross-sectional helpers: a wide close-price panel across many tickers and its
  correlation matrix.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

try:
    import numpy as np
    import pandas as pd
    HAS_PANDAS = True
except Exception:  # pragma: no cover
    np = None
    pd = None
    HAS_PANDAS = False

from ..config import TRADING_DAYS_PER_YEAR
from ..databases.store import Bar, MarketStore


def _require() -> None:
    if not HAS_PANDAS:
        raise RuntimeError(
            "pandas is required for this feature. Install it with "
            "`pip install pandas` (the rest of AOA-Financial runs without it).")


# -- IO -------------------------------------------------------------------
def bars_to_frame(bars: Sequence[Bar]) -> "pd.DataFrame":
    """Convert a list of ``Bar`` into a DatetimeIndexed OHLCV frame."""
    _require()
    df = pd.DataFrame(
        {
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        },
        index=pd.to_datetime([b.date for b in bars]),
    )
    df.index.name = "date"
    return df


def frame_to_bars(df: "pd.DataFrame") -> List[Bar]:
    """Inverse of :func:`bars_to_frame` — for ingesting external data."""
    _require()
    out: List[Bar] = []
    for idx, row in df.iterrows():
        date = idx.date().isoformat() if hasattr(idx, "date") else str(idx)
        out.append(Bar(date, float(row["open"]), float(row["high"]),
                       float(row["low"]), float(row["close"]),
                       int(row["volume"])))
    return out


def store_frame(store: MarketStore, ticker: str,
                start: Optional[str] = None,
                end: Optional[str] = None) -> "pd.DataFrame":
    """Load a ticker's history from the store into a DataFrame."""
    return bars_to_frame(store.get_bars(ticker, start=start, end=end))


def write_csv(store: MarketStore, ticker: str, path: str) -> int:
    df = indicator_frame(store_frame(store, ticker))
    df.to_csv(path)
    return len(df)


def read_csv(path: str) -> "pd.DataFrame":
    _require()
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return df


# -- vectorised indicators ------------------------------------------------
def _wilder(series: "pd.Series", period: int) -> "pd.Series":
    """Wilder's smoothing (RMA): EMA with alpha = 1/period."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def rsi(close: "pd.Series", period: int = 14) -> "pd.Series":
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder(gain, period)
    avg_loss = _wilder(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(avg_loss != 0.0, 100.0)


def macd(close: "pd.Series", fast: int = 12, slow: int = 26,
         signal: int = 9) -> "pd.DataFrame":
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "macd_signal": sig,
                         "macd_hist": line - sig})


def atr(df: "pd.DataFrame", period: int = 14) -> "pd.Series":
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return _wilder(tr, period)


def indicator_frame(df: "pd.DataFrame") -> "pd.DataFrame":
    """Augment an OHLCV frame with the full vectorised indicator suite."""
    _require()
    out = df.copy()
    close = out["close"]

    out["log_return"] = np.log(close / close.shift(1))
    out["sma_50"] = close.rolling(50).mean()
    out["sma_200"] = close.rolling(200).mean()
    out["ema_12"] = close.ewm(span=12, adjust=False).mean()
    out["ema_26"] = close.ewm(span=26, adjust=False).mean()
    out["golden_cross"] = out["sma_50"] > out["sma_200"]
    out["rsi_14"] = rsi(close, 14)
    out = out.join(macd(close))

    mid = close.rolling(20).mean()
    sd = close.rolling(20).std()  # ddof=1, matches scalar S.stdev
    out["bb_upper"] = mid + 2.0 * sd
    out["bb_lower"] = mid - 2.0 * sd
    width = (out["bb_upper"] - out["bb_lower"])
    out["bb_pct_b"] = (close - out["bb_lower"]) / width.replace(0.0, np.nan)

    out["atr_14"] = atr(out, 14)
    out["vol_21"] = out["log_return"].rolling(21).std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    out["vol_252"] = out["log_return"].rolling(252).std() * np.sqrt(TRADING_DAYS_PER_YEAR)
    out["drawdown"] = close / close.cummax() - 1.0
    out["mom_21"] = close / close.shift(21) - 1.0
    out["mom_252"] = close / close.shift(252) - 1.0
    return out


def latest_indicators(df: "pd.DataFrame") -> dict:
    """The most recent row of :func:`indicator_frame` as a plain dict."""
    ind = indicator_frame(df)
    row = ind.iloc[-1]
    return {k: (None if pd.isna(v) else (bool(v) if isinstance(v, (bool, np.bool_))
                else float(v)))
            for k, v in row.items()}


# -- cross-sectional ------------------------------------------------------
def close_panel(store: MarketStore, tickers: Iterable[str]) -> "pd.DataFrame":
    """Wide panel of aligned close prices: one column per ticker."""
    _require()
    cols = {}
    for t in tickers:
        bars = store.get_bars(t)
        if bars:
            s = pd.Series({pd.Timestamp(b.date): b.close for b in bars})
            cols[t.upper()] = s
    panel = pd.DataFrame(cols).sort_index()
    panel.index.name = "date"
    return panel


def correlation_matrix(store: MarketStore, tickers: Iterable[str],
                       window: Optional[int] = 252) -> "pd.DataFrame":
    """Correlation of daily log returns across the given tickers."""
    panel = close_panel(store, tickers)
    rets = np.log(panel / panel.shift(1))
    if window:
        rets = rets.tail(window)
    return rets.corr()
