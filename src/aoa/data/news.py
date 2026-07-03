"""News service: fetches and caches Alpaca headlines per symbol for agent prompts."""

from __future__ import annotations

from aoa.brokerage.base import Broker
from aoa.brokerage.models import NewsItem


class NewsService:
    """Fetches broker news once per cycle and groups headlines by ticker."""

    def __init__(
        self,
        broker: Broker,
        *,
        limit_per_symbol: int = 5,
        lookback_hours: int = 72,
    ) -> None:
        self.broker = broker
        self.limit_per_symbol = limit_per_symbol
        self.lookback_hours = lookback_hours
        self._cache: dict[str, list[NewsItem]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def fetch(self, symbols: list[str]) -> dict[str, list[NewsItem]]:
        """Return up to ``limit_per_symbol`` headlines per symbol (newest first)."""
        normalized = [s.upper() for s in symbols if s]
        missing = [s for s in normalized if s not in self._cache]
        if missing:
            batch_limit = max(50, self.limit_per_symbol * len(missing))
            articles = self.broker.get_news(
                missing,
                limit=batch_limit,
                lookback_hours=self.lookback_hours,
            )
            grouped: dict[str, list[NewsItem]] = {s: [] for s in missing}
            for article in articles:
                for sym in article.symbols:
                    if sym in grouped and len(grouped[sym]) < self.limit_per_symbol:
                        grouped[sym].append(article)
            for sym in missing:
                self._cache[sym] = grouped[sym]
        return {s: list(self._cache.get(s, [])) for s in normalized}
