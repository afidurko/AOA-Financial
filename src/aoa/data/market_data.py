"""Market-data service: assembles a per-symbol snapshot from the broker.

This layer caches within a single swarm cycle so repeated agent lookups of the
same symbol do not hammer the data API. Bars are fetched across multiple
timeframes (1m → yearly) and condensed into per-timeframe technical snapshots.
"""

from __future__ import annotations

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
    ) -> None:
        self.broker = broker
        self.timeframes = timeframes
        self._cache: dict[str, SymbolSnapshot] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def snapshot(self, symbol: str) -> SymbolSnapshot:
        symbol = symbol.upper()
        if symbol in self._cache:
            return self._cache[symbol]
        snap = self._build(symbol)
        self._cache[symbol] = snap
        return snap

    def snapshots(self, symbols: list[str]) -> dict[str, SymbolSnapshot]:
        normalized = [s.upper() for s in symbols if s]
        if not normalized:
            return {}

        missing = [s for s in normalized if s not in self._cache]
        bars_by_tf_symbol: dict[str, dict[str, list[Bar]]] = {}
        if missing:
            for tf in self.timeframes:
                batch = self.broker.get_bars_many(missing, tf.alpaca, tf.limit)
                bars_by_tf_symbol[tf.key] = batch

        out: dict[str, SymbolSnapshot] = {}
        for sym in normalized:
            if sym in self._cache:
                out[sym] = self._cache[sym]
                continue
            tf_bars = {
                tf.key: bars_by_tf_symbol.get(tf.key, {}).get(sym, [])
                for tf in self.timeframes
            }
            snap = self._build(sym, bars_by_timeframe=tf_bars)
            self._cache[sym] = snap
            out[sym] = snap
        return out

    def _build(
        self,
        symbol: str,
        *,
        bars_by_timeframe: dict[str, list[Bar]] | None = None,
    ) -> SymbolSnapshot:
        try:
            quote = self.broker.get_quote(symbol)
            if bars_by_timeframe is None:
                bars_by_timeframe = {}
                for tf in self.timeframes:
                    bars_by_timeframe[tf.key] = self.broker.get_bars(
                        symbol, tf.alpaca, tf.limit
                    )
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
