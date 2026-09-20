"""Public candle providers with a CSV cache and a seeded synthetic fallback.

Providers (all keyless, stdlib ``urllib`` only):

* ``yahoo``    — Yahoo Finance v8 chart API. US equities, ETFs and crypto
  (``BTC-USD``). Intraday history is limited by Yahoo (1m → 7 days,
  5m/15m/30m → 60 days, 60m → 730 days, 1d → decades).
* ``kraken``   — Kraken public OHLC (crypto; up to 720 most-recent candles per
  call, intervals 1/5/15/30/60/240/1440/10080 minutes).
* ``coinbase`` — Coinbase Exchange public candles (crypto; paginated in
  300-candle windows, granularity 60/300/900/3600/21600/86400 seconds).
* ``synthetic``— deterministic regime-switching GBM with intraday seasonality
  so the whole lane works offline and in tests.

Every fetch is cached under ``<cache_dir>/<source>/<symbol>_<tf>.csv`` and
merged with what is already on disk, so repeated sweeps do not re-download and
the desk's history keeps growing between runs (persistence).
"""

from __future__ import annotations

import csv
import json
import math
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aoa.brokerage.models import Bar
from aoa.tradingview.presets import Timeframe, get_timeframe

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AOA-Financial/tradingview-desk"
DEFAULT_CACHE_DIR = Path("data") / "tradingview" / "cache"
SOURCES = ("auto", "yahoo", "kraken", "coinbase", "synthetic")


class DataError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def _get_json(url: str, *, timeout: float = 20.0, retries: int = 3, backoff: float = 1.5) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
                continue
            raise DataError(f"HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
                continue
    raise DataError(f"request failed for {url}: {last}")


# --------------------------------------------------------------------------- #
# Parsers (pure, unit-testable)
# --------------------------------------------------------------------------- #


def _ts(epoch: float) -> datetime:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc)


def parse_yahoo_chart(payload: dict[str, Any]) -> list[Bar]:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise DataError(f"yahoo: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        return []
    res = results[0]
    stamps = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    vols = quote.get("volume") or []
    out: list[Bar] = []
    for i, ts in enumerate(stamps):
        try:
            o, h, lo, c = opens[i], highs[i], lows[i], closes[i]
        except IndexError:
            break
        if None in (o, h, lo, c):
            continue
        v = vols[i] if i < len(vols) and vols[i] is not None else 0.0
        out.append(Bar(_ts(ts), float(o), float(h), float(lo), float(c), float(v)))
    return out


def parse_kraken_ohlc(payload: dict[str, Any]) -> list[Bar]:
    if payload.get("error"):
        raise DataError(f"kraken: {payload['error']}")
    result = payload.get("result") or {}
    rows: list[list[Any]] = []
    for key, value in result.items():
        if key == "last":
            continue
        rows = value
        break
    out: list[Bar] = []
    for row in rows:
        # [time, open, high, low, close, vwap, volume, count]
        out.append(
            Bar(_ts(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[6]))
        )
    return out


def parse_coinbase_candles(payload: list[list[Any]]) -> list[Bar]:
    out: list[Bar] = []
    for row in payload:
        # [time, low, high, open, close, volume] newest first
        out.append(Bar(_ts(row[0]), float(row[3]), float(row[2]), float(row[1]), float(row[4]), float(row[5])))
    out.sort(key=lambda b: b.timestamp)
    return out


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #


def fetch_yahoo(symbol: str, tf: Timeframe, *, range_: str | None = None) -> list[Bar]:
    if not tf.yahoo:
        raise DataError(f"yahoo has no {tf.label} interval")
    params = urllib.parse.urlencode(
        {"interval": tf.yahoo, "range": range_ or tf.yahoo_range or "1y", "includePrePost": "false"}
    )
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{params}"
    return parse_yahoo_chart(_get_json(url))


def fetch_kraken(pair: str, tf: Timeframe, *, since: int | None = None) -> list[Bar]:
    if not tf.kraken:
        raise DataError(f"kraken has no {tf.label} interval")
    q = {"pair": pair, "interval": tf.kraken}
    if since:
        q["since"] = since
    url = f"https://api.kraken.com/0/public/OHLC?{urllib.parse.urlencode(q)}"
    return parse_kraken_ohlc(_get_json(url))


def fetch_coinbase(product: str, tf: Timeframe, *, limit: int = 3000) -> list[Bar]:
    if not tf.coinbase:
        raise DataError(f"coinbase has no {tf.label} granularity")
    gran = tf.coinbase
    end = datetime.now(tz=timezone.utc).replace(microsecond=0)
    out: list[Bar] = []
    remaining = limit
    while remaining > 0:
        n = min(300, remaining)
        start = end - timedelta(seconds=gran * n)
        q = urllib.parse.urlencode({"granularity": gran, "start": start.isoformat(), "end": end.isoformat()})
        url = f"https://api.exchange.coinbase.com/products/{urllib.parse.quote(product)}/candles?{q}"
        chunk = parse_coinbase_candles(_get_json(url))
        if not chunk:
            break
        out = chunk + out
        remaining -= len(chunk)
        end = chunk[0].timestamp - timedelta(seconds=gran)
        time.sleep(0.25)
    return dedupe_bars(out)


def synthetic_bars(
    symbol: str,
    tf: Timeframe,
    *,
    n: int = 2000,
    seed: int | None = None,
    start_price: float = 100.0,
    market: str = "equity",
) -> list[Bar]:
    """Seeded regime-switching GBM with volume clustering (offline fallback)."""
    rng = random.Random(seed if seed is not None else hash((symbol, tf.key)) & 0xFFFF)
    dt_years = tf.seconds / (365 * 86400 if market == "crypto" else 252 * 6.5 * 3600)
    regimes = [(0.10, 0.18), (0.30, 0.25), (-0.25, 0.45), (0.0, 0.12)]
    mu, sigma = regimes[0]
    price = start_price
    ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    step = timedelta(seconds=tf.seconds)
    out: list[Bar] = []
    for _ in range(n):
        if rng.random() < 0.01:
            mu, sigma = rng.choice(regimes)
        shock = rng.gauss(0.0, 1.0)
        if rng.random() < 0.003:
            shock *= 4.0
        ret = (mu - 0.5 * sigma**2) * dt_years + sigma * math.sqrt(dt_years) * shock
        o = price
        c = max(price * math.exp(ret), 0.01)
        wick = abs(c - o) * rng.uniform(0.2, 1.2) + price * sigma * math.sqrt(dt_years) * 0.3
        h = max(o, c) + wick * rng.random()
        lo = min(o, c) - wick * rng.random()
        base_vol = 1_000_000 if market == "equity" else 250.0
        v = base_vol * (0.5 + rng.random()) * (1.0 + 3.0 * abs(shock) / 3.0)
        out.append(Bar(ts, round(o, 6), round(h, 6), round(max(lo, 0.005), 6), round(c, 6), round(v, 4)))
        price = c
        ts += step
    return out


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #


def dedupe_bars(bars: Iterable[Bar]) -> list[Bar]:
    by_ts: dict[datetime, Bar] = {}
    for b in bars:
        by_ts[b.timestamp] = b
    return [by_ts[k] for k in sorted(by_ts)]


def _cache_path(cache_dir: Path, source: str, symbol: str, tf: Timeframe) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in symbol)
    return cache_dir / source / f"{safe}_{tf.key}.csv"


def read_cache(path: Path) -> list[Bar]:
    if not path.is_file():
        return []
    out: list[Bar] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out.append(
                    Bar(
                        datetime.fromisoformat(row["timestamp"]),
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["volume"]),
                    )
                )
            except (KeyError, ValueError):
                continue
    return out


def write_cache(path: Path, bars: list[Bar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume])


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #

_CRYPTO_HINTS = ("-USD", "-USDT", "USDT", "XBT", "BTC", "ETH", "SOL", "/")


def guess_market(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith("-USD") or s.endswith("-USDT") or s.endswith("USDT") or "/" in s:
        return "crypto"
    if s.startswith(("XBT", "XETH", "XXBT")) or s in {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE"}:
        return "crypto"
    return "equity"


def to_kraken_pair(symbol: str) -> str:
    s = symbol.upper().replace("-", "").replace("/", "")
    return {"BTCUSD": "XBTUSD", "BTCUSDT": "XBTUSDT"}.get(s, s)


def to_coinbase_product(symbol: str) -> str:
    s = symbol.upper().replace("/", "-")
    if "-" not in s and s.endswith("USD"):
        s = f"{s[:-3]}-USD"
    return s.replace("XBT", "BTC")


def fetch_bars(
    symbol: str,
    timeframe: str | Timeframe,
    *,
    source: str = "auto",
    limit: int | None = None,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
    refresh: bool = True,
    seed: int | None = None,
    market: str | None = None,
    synthetic_n: int = 2000,
) -> tuple[list[Bar], str]:
    """Return ``(bars, source_used)`` for ``symbol`` at ``timeframe``.

    ``source="auto"`` prefers Yahoo for equities and Kraken → Coinbase → Yahoo
    for crypto, and silently falls back to the synthetic generator only when
    every network provider fails (the returned source tells you which).
    """
    tf = timeframe if isinstance(timeframe, Timeframe) else get_timeframe(timeframe)
    market = market or guess_market(symbol)
    cache_root = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    if source not in SOURCES:
        raise DataError(f"unknown source {source!r}; choose from {SOURCES}")

    if source == "synthetic":
        bars = synthetic_bars(symbol, tf, n=synthetic_n, seed=seed, market=market)
        return (bars[-limit:] if limit else bars), "synthetic"

    order: list[str]
    if source == "auto":
        order = ["kraken", "coinbase", "yahoo"] if market == "crypto" else ["yahoo"]
    else:
        order = [source]

    errors: list[str] = []
    for src in order:
        path = _cache_path(cache_root, src, symbol, tf)
        cached = read_cache(path) if use_cache else []
        fresh: list[Bar] = []
        if refresh or not cached:
            try:
                if src == "yahoo":
                    fresh = fetch_yahoo(symbol, tf)
                elif src == "kraken":
                    fresh = fetch_kraken(to_kraken_pair(symbol), tf)
                elif src == "coinbase":
                    fresh = fetch_coinbase(to_coinbase_product(symbol), tf, limit=limit or 3000)
            except DataError as exc:
                errors.append(f"{src}: {exc}")
                fresh = []
        merged = dedupe_bars([*cached, *fresh])
        if fresh and use_cache:
            write_cache(path, merged)
        if merged:
            return (merged[-limit:] if limit else merged), src
    bars = synthetic_bars(symbol, tf, n=synthetic_n, seed=seed, market=market)
    note = "; ".join(errors) if errors else "no provider"
    return (bars[-limit:] if limit else bars), f"synthetic ({note})"
