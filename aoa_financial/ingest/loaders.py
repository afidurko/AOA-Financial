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


def ingest_ticker(store: MarketStore, ticker: str, *, end: date | None = None,
                  prefer_live: bool = False, refresh: bool = False) -> dict:
    """Ensure ``ticker`` has history in the store.

    Returns a small report dict: source used, number of bars, sector.
    """
    ticker = ticker.upper()
    if store.has_prices(ticker) and not refresh:
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
    return {"ticker": ticker, "source": source, "bars": n,
            "sector": sector, "cached": False}


def ingest_universe(store: MarketStore, tickers: List[str], *,
                    prefer_live: bool = False) -> List[dict]:
    return [ingest_ticker(store, t, prefer_live=prefer_live) for t in tickers]
