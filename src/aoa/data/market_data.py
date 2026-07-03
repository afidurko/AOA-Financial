"""Market-data service: assembles a per-symbol snapshot from the broker.

This layer caches within a single swarm cycle so repeated agent lookups of the
same symbol do not hammer the data API. Bars are fetched across multiple
timeframes (1m → yearly) and condensed into per-timeframe technical snapshots.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from aoa.brokerage.base import Broker, BrokerError
from aoa.brokerage.models import Bar, Quote
from aoa.data.indicators import technical_snapshot
from aoa.data.timeframes import DEFAULT_TIMEFRAMES, TimeframeSpec

PRIMARY_TIMEFRAME = "1Day"


@dataclass
class SymbolSnapshot:
    symbol: str
    quote: Quote | None
    bars: list[Bar] = field(default_factory=list)
    bars_by_timeframe: dict[str, list[Bar]] = field(default_factory=dict)
    technicals: dict[str, dict] = field(default_factory=dict)
    error: str | None = None

    @property
    def has_technicals(self) -> bool:
        return any(t.get("last_close") for t in self.technicals.values())

    def last_close(self) -> float | None:
        daily = self.technicals.get(PRIMARY_TIMEFRAME, {})
        return daily.get("last_close")

    def reference_price(self) -> float | None:
        """Best available mark: quote mid, else last bar close."""
        if self.quote:
            mid = self.quote.mid
            if mid and mid > 0:
                return mid
        last = self.last_close()
        if last and last > 0:
            return float(last)
        return None

    def to_context(self) -> dict:
        """Compact JSON-serializable view for prompting the agents."""
        q = self.quote
        return {
            "symbol": self.symbol,
            "quote": (
                {
                    "bid": q.bid,
                    "ask": q.ask,
                    "mid": q.mid,
                    "spread": q.spread,
                }
                if q
                else None
            ),
            "primary_timeframe": PRIMARY_TIMEFRAME,
            "technicals": self.technicals,
            "error": self.error,
        }


class MarketDataService:
    def __init__(
        self,
        broker: Broker,
        *,
        timeframes: tuple[TimeframeSpec, ...] = DEFAULT_TIMEFRAMES,
        bar_feed: str | None = None,
    ) -> None:
        self.broker = broker
        self.timeframes = timeframes
        self.bar_feed = bar_feed
        self._cache: dict[str, SymbolSnapshot] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def snapshot(self, symbol: str) -> SymbolSnapshot:
        symbol = symbol.upper()
        if symbol in self._cache:
            return self._cache[symbol]
        snaps = self.snapshots([symbol])
        return snaps[symbol]

    def snapshots(self, symbols: list[str]) -> dict[str, SymbolSnapshot]:
        normalized = [s.upper() for s in symbols if s]
        if not normalized:
            return {}

        missing = [s for s in normalized if s not in self._cache]
        quotes_by_symbol: dict[str, Quote] = {}
        bars_by_tf_symbol: dict[str, dict[str, list[Bar]]] = {}

        if missing:
            try:
                quotes_by_symbol = self.broker.get_quotes_many(missing)
            except BrokerError:
                quotes_by_symbol = {}

            bars_by_tf_symbol = self._fetch_bars_parallel(missing)

        out: dict[str, SymbolSnapshot] = {}
        for sym in normalized:
            if sym in self._cache:
                out[sym] = self._cache[sym]
                continue
            tf_bars = {
                tf.key: bars_by_tf_symbol.get(tf.key, {}).get(sym, [])
                for tf in self.timeframes
            }
            snap = self._assemble(
                sym,
                quote=quotes_by_symbol.get(sym),
                bars_by_timeframe=tf_bars,
            )
            self._cache[sym] = snap
            out[sym] = snap
        return out

    def _fetch_bars_parallel(
        self, symbols: list[str]
    ) -> dict[str, dict[str, list[Bar]]]:
        bars_by_tf_symbol: dict[str, dict[str, list[Bar]]] = {}
        if not self.timeframes:
            return bars_by_tf_symbol

        def fetch(tf: TimeframeSpec) -> tuple[str, dict[str, list[Bar]]]:
            batch = self.broker.get_bars_batch(symbols, tf.alpaca, tf.limit)
            return tf.key, batch

        max_workers = min(len(self.timeframes), 8)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(fetch, tf) for tf in self.timeframes]
            for fut in as_completed(futures):
                key, batch = fut.result()
                bars_by_tf_symbol[key] = batch
        return bars_by_tf_symbol

    def _assemble(
        self,
        symbol: str,
        *,
        quote: Quote | None,
        bars_by_timeframe: dict[str, list[Bar]],
    ) -> SymbolSnapshot:
        try:
            if quote is None:
                quote = self.broker.get_quote(symbol)
            technicals = {
                tf: technical_snapshot(bars) if bars else {}
                for tf, bars in bars_by_timeframe.items()
            }
            daily_bars = bars_by_timeframe.get(PRIMARY_TIMEFRAME, [])
            return SymbolSnapshot(
                symbol=symbol,
                quote=quote,
                bars=daily_bars,
                bars_by_timeframe=bars_by_timeframe,
                technicals=technicals,
            )
        except BrokerError as exc:
            return SymbolSnapshot(symbol=symbol, quote=None, error=str(exc))
