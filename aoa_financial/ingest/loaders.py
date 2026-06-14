"""High-level ingestion orchestration.

``ingest_ticker`` tries an optional live source (Stooq's free CSV endpoint)
and, on any failure (no network, unknown symbol, rate limit), transparently
falls back to the deterministic synthetic generator so the pipeline is never
blocked. Either way the result lands in the :class:`MarketStore` consistently.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import List, Optional

from ..databases.store import Bar, MarketStore, Security
from .synthetic import SyntheticGenerator
from .fundamentals_feed import fetch_fundamentals, FIELDS as _FUND_FIELDS

_STOOQ_URL = "https://stooq.com/q/d/l/?s={sym}.us&i=d"


def _try_stooq(ticker: str, timeout: float = 8.0) -> Optional[List[Bar]]:
    """Attempt to fetch real daily history from Stooq. Returns None on failure."""
    try:
        import requests  # optional dependency
    except Exception:
        return None
    try:
        url = _STOOQ_URL.format(sym=ticker.lower())
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200 or "Date,Open" not in resp.text[:64]:
            return None
        bars: List[Bar] = []
        reader = csv.DictReader(io.StringIO(resp.text))
        for row in reader:
            try:
                bars.append(Bar(
                    date=row["Date"],
                    open=float(row["Open"]), high=float(row["High"]),
                    low=float(row["Low"]), close=float(row["Close"]),
                    volume=int(float(row.get("Volume", 0) or 0)),
                ))
            except (ValueError, KeyError):
                continue
        return bars or None
    except Exception:
        return None


def refresh_fundamentals(store: MarketStore, ticker: str, *,
                         provider: Optional[str] = None,
                         asof: Optional[str] = None) -> dict:
    """Fetch (live or synthetic) fundamentals and upsert them into the store.

    Returns the result dict from :func:`fetch_fundamentals` (includes the
    ``provider`` actually used). Never raises on network failure — it falls
    back to synthetic.
    """
    ticker = ticker.upper()
    result = fetch_fundamentals(ticker, provider=provider)
    if asof is None:
        bars = store.get_bars(ticker, limit=1)
        asof = bars[-1].date if bars else date.today().isoformat()
    payload = {k: result.get(k) for k in _FUND_FIELDS}
    store.upsert_fundamentals(ticker, asof, payload)
    return result


def ingest_ticker(store: MarketStore, ticker: str, *, end: date | None = None,
                  prefer_live: bool = False, refresh: bool = False,
                  live_fundamentals: bool = False,
                  fundamentals_provider: Optional[str] = None) -> dict:
    """Ensure ``ticker`` has history in the store.

    Returns a small report dict: source used, number of bars, sector. When
    ``live_fundamentals`` is set, fundamentals are (re)fetched from the
    configured provider after price ingest.
    """
    ticker = ticker.upper()
    if store.has_prices(ticker) and not refresh:
        if live_fundamentals:
            refresh_fundamentals(store, ticker, provider=fundamentals_provider)
        existing = store.get_bars(ticker)
        sec = store.get_security(ticker)
        return {"ticker": ticker, "source": sec.source if sec else "cached",
                "bars": len(existing), "sector": sec.sector if sec else "?",
                "cached": True}

    source = "synthetic"
    bars: Optional[List[Bar]] = None
    sector = "Unknown"
    gen = SyntheticGenerator()

    if prefer_live:
        bars = _try_stooq(ticker)
        if bars:
            source = "stooq"

    if not bars:
        series = gen.generate(ticker, end=end)
        bars = series.bars
        sector = series.sector
        # Persist synthetic fundamentals + sentiment too.
        store.upsert_security(Security(
            ticker=ticker, name=f"{ticker} (synthetic)", sector=sector,
            listed_on=bars[0].date, source=source, meta={"generated": True}))
        store.upsert_fundamentals(ticker, bars[-1].date, series.fundamentals)
        store.upsert_sentiment(ticker, bars[-1].date, series.sentiment,
                               volume=0, source="synthetic")
    else:
        store.upsert_security(Security(
            ticker=ticker, name=ticker, sector=sector,
            listed_on=bars[0].date, source=source, meta={"live": True}))

    n = store.insert_bars(ticker, bars)
    if live_fundamentals:
        refresh_fundamentals(store, ticker, provider=fundamentals_provider,
                             asof=bars[-1].date)
    return {"ticker": ticker, "source": source, "bars": n,
            "sector": sector, "cached": False}


def ingest_universe(store: MarketStore, tickers: List[str], *,
                    prefer_live: bool = False) -> List[dict]:
    return [ingest_ticker(store, t, prefer_live=prefer_live) for t in tickers]


def ingest_dataframe(store: MarketStore, ticker: str, df, *,
                     sector: str = "Unknown", name: Optional[str] = None) -> dict:
    """Ingest an external pandas DataFrame (OHLCV, DatetimeIndex) into the store.

    Lets callers bring their own data — a CSV, a vendor feed, a research panel —
    and have it analysed by the rest of the engine identically to synthetic or
    Stooq history. Requires the optional pandas layer.
    """
    from ..analysis.frames import frame_to_bars, HAS_PANDAS
    if not HAS_PANDAS:
        raise RuntimeError("pandas is required for ingest_dataframe")
    ticker = ticker.upper()
    bars = frame_to_bars(df)
    if not bars:
        raise ValueError("empty dataframe")
    store.upsert_security(Security(
        ticker=ticker, name=name or ticker, sector=sector,
        listed_on=bars[0].date, source="dataframe", meta={"imported": True}))
    n = store.insert_bars(ticker, bars)
    return {"ticker": ticker, "source": "dataframe", "bars": n, "sector": sector,
            "cached": False}
