"""Daily crypto history: fetch, merge, cache, and calendar-walk.

Two free, keyless sources with different depth:

* **Bitstamp** public OHLC (``/api/v2/ohlc``) — BTC/USD back to 2011-08,
  paginated 1000 daily candles per call.
* **Yahoo Finance** v8 chart (``range=max``) — BTC-USD from 2014-09, ETH-USD
  and XRP-USD from 2017-11, SOL-USD from 2020-04.

Histories are merged per-date (earliest-listing source wins on conflicts,
which in practice means Bitstamp for early BTC) and cached as JSON under
``data/crypto/`` so training runs are reproducible and offline-friendly.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from aoa.crypto.assets import TRAINING_EPOCH, CryptoAsset

_BITSTAMP_URL = "https://www.bitstamp.net/api/v2/ohlc/{pair}/"
_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_DAY = 86400


@dataclass(frozen=True)
class DailyCandle:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DailyCandle:
        return cls(
            day=date.fromisoformat(data["day"]),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data.get("volume", 0.0)),
            source=str(data.get("source", "")),
        )


def _http_get(url: str, params: dict | None = None) -> dict:
    from aoa.httpcompat import httpx

    resp = httpx.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0 (aoa-financial research)"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_bitstamp_daily(pair: str, *, start: date | None = None) -> list[DailyCandle]:
    """Fetch the full daily OHLC history for a Bitstamp pair (paginated)."""
    begin = int(
        datetime.combine(start or date(2011, 1, 1), datetime.min.time(), timezone.utc).timestamp()
    )
    now = int(datetime.now(timezone.utc).timestamp())
    out: dict[date, DailyCandle] = {}
    # NB: Bitstamp's ``limit`` counts *window* days from ``start`` (empty
    # pre-listing days included), so a page may return fewer than ``limit``
    # rows mid-history. Paginate on the window, not the row count.
    while begin < now:
        payload = _http_get(
            _BITSTAMP_URL.format(pair=pair),
            params={"step": _DAY, "limit": 1000, "start": begin},
        )
        rows = payload.get("data", {}).get("ohlc", [])
        for row in rows:
            ts = int(row["timestamp"])
            day = datetime.fromtimestamp(ts, timezone.utc).date()
            out[day] = DailyCandle(
                day=day,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                source="bitstamp",
            )
        window_end = begin + 1000 * _DAY
        last_ts = int(rows[-1]["timestamp"]) if rows else begin
        next_begin = max(window_end, last_ts + _DAY)
        if next_begin <= begin:
            break
        begin = next_begin
    return [out[d] for d in sorted(out)]


def fetch_yahoo_daily(symbol: str) -> list[DailyCandle]:
    """Fetch the full daily history for a Yahoo Finance crypto symbol.

    Uses explicit ``period1/period2`` — ``range=max`` silently downgrades the
    granularity to monthly, while an explicit epoch range keeps it daily.
    """
    payload = _http_get(
        _YAHOO_URL.format(symbol=symbol),
        params={
            "period1": 0,
            "period2": int(datetime.now(timezone.utc).timestamp()),
            "interval": "1d",
            "events": "history",
        },
    )
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        return []
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    out: dict[date, DailyCandle] = {}
    for i, ts in enumerate(stamps):
        try:
            o, h, lo, c = opens[i], highs[i], lows[i], closes[i]
        except IndexError:
            continue
        if None in (o, h, lo, c) or c <= 0:
            continue
        day = datetime.fromtimestamp(int(ts), timezone.utc).date()
        vol = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0
        out[day] = DailyCandle(
            day=day,
            open=float(o),
            high=float(h),
            low=float(lo),
            close=float(c),
            volume=float(vol),
            source="yahoo",
        )
    return [out[d] for d in sorted(out)]


def merge_histories(*histories: Sequence[DailyCandle]) -> list[DailyCandle]:
    """Merge per-date; earlier-listed histories take precedence on conflicts."""
    merged: dict[date, DailyCandle] = {}
    ordered = sorted(
        (list(h) for h in histories if h),
        key=lambda h: h[0].day,
    )
    for hist in reversed(ordered):  # earliest-starting source applied last → wins
        for candle in hist:
            merged[candle.day] = candle
    return [merged[d] for d in sorted(merged)]


class HistoryStore:
    """JSON-cached daily histories under ``data/crypto/``."""

    def __init__(self, root: str | Path = "data/crypto") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, asset: CryptoAsset) -> Path:
        return self.root / f"{asset.code.lower()}_daily.json"

    def load(self, asset: CryptoAsset) -> list[DailyCandle]:
        path = self.path_for(asset)
        if not path.exists():
            return []
        raw = json.loads(path.read_text())
        return [DailyCandle.from_dict(row) for row in raw.get("candles", [])]

    def save(self, asset: CryptoAsset, candles: Sequence[DailyCandle]) -> Path:
        path = self.path_for(asset)
        path.write_text(
            json.dumps(
                {
                    "asset": asset.code,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "candles": [c.to_dict() for c in candles],
                }
            )
        )
        return path

    def fetch(self, asset: CryptoAsset) -> list[DailyCandle]:
        """Fetch from every available source and merge."""
        histories: list[list[DailyCandle]] = []
        errors: list[str] = []
        if asset.bitstamp_pair:
            try:
                histories.append(fetch_bitstamp_daily(asset.bitstamp_pair))
            except Exception as exc:  # noqa: BLE001 — source-level resilience
                errors.append(f"bitstamp: {exc}")
        try:
            histories.append(fetch_yahoo_daily(asset.yahoo_symbol))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"yahoo: {exc}")
        merged = merge_histories(*histories)
        if not merged:
            raise RuntimeError(
                f"No history available for {asset.code} ({'; '.join(errors) or 'no sources'})"
            )
        return merged

    def ensure(self, asset: CryptoAsset, *, refresh: bool = False) -> list[DailyCandle]:
        """Load from cache, fetching (and caching) when missing or refreshing."""
        if not refresh:
            cached = self.load(asset)
            if cached:
                return cached
        candles = self.fetch(asset)
        self.save(asset, candles)
        return candles


@dataclass(frozen=True)
class CalendarDay:
    """One day of the training walk: a candle, or the reason there is none."""

    day: date
    candle: DailyCandle | None
    status: str  # "market" | "pre-genesis" | "pre-market" | "gap"


def calendar_walk(
    asset: CryptoAsset,
    candles: Sequence[DailyCandle],
    *,
    start: date = TRAINING_EPOCH,
    end: date | None = None,
) -> Iterator[CalendarDay]:
    """Walk *every* calendar day from ``start``, labeling non-market days.

    This is the honest version of "train since 2007-07-17": days before an
    asset's genesis/first market are yielded explicitly (so the learner knows
    the asset did not exist) instead of silently skipped, and data gaps inside
    the market era are labeled ``"gap"``.
    """
    by_day = {c.day: c for c in candles}
    last = end or (candles[-1].day if candles else start)
    day = start
    while day <= last:
        candle = by_day.get(day)
        if candle is not None:
            status = "market"
        elif asset.genesis and day < asset.genesis:
            status = "pre-genesis"
        elif day < asset.first_market:
            status = "pre-market"
        elif candles and day < candles[0].day:
            # After first_market but before our earliest data source coverage.
            status = "pre-market"
        else:
            status = "gap"
        yield CalendarDay(day=day, candle=candle, status=status)
        day += timedelta(days=1)
