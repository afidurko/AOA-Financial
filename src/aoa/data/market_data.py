"""Market-data service: assembles a per-symbol snapshot from the broker.

This layer caches within a single swarm cycle so repeated agent lookups of the
same symbol do not hammer the data API.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aoa.brokerage.base import Broker, BrokerError
from aoa.brokerage.models import Bar, Quote
from aoa.data.indicators import technical_snapshot


@dataclass
class SymbolSnapshot:
    symbol: str
    quote: Quote | None
    bars: list[Bar] = field(default_factory=list)
    technicals: dict = field(default_factory=dict)
    error: str | None = None

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
            "technicals": self.technicals,
            "error": self.error,
        }


class MarketDataService:
    def __init__(self, broker: Broker, *, bar_timeframe: str = "1Day", bar_limit: int = 220):
        self.broker = broker
        self.bar_timeframe = bar_timeframe
        self.bar_limit = bar_limit
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
        uncached = [s for s in normalized if s not in self._cache]
        if uncached:
            try:
                bars_map = self.broker.get_bars_batch(
                    uncached, self.bar_timeframe, self.bar_limit
                )
            except BrokerError as exc:
                for symbol in uncached:
                    self._cache[symbol] = SymbolSnapshot(
                        symbol=symbol, quote=None, error=str(exc)
                    )
            else:
                for symbol in uncached:
                    self._cache[symbol] = self._build(
                        symbol, bars=bars_map.get(symbol, [])
                    )
        return {s: self._cache[s] for s in normalized if s in self._cache}

    def _build(
        self,
        symbol: str,
        *,
        bars: list[Bar] | None = None,
    ) -> SymbolSnapshot:
        try:
            quote = self.broker.get_quote(symbol)
            if bars is None:
                bars = self.broker.get_bars(symbol, self.bar_timeframe, self.bar_limit)
            technicals = technical_snapshot(bars) if bars else {}
            return SymbolSnapshot(symbol=symbol, quote=quote, bars=bars, technicals=technicals)
        except BrokerError as exc:
            return SymbolSnapshot(symbol=symbol, quote=None, error=str(exc))
