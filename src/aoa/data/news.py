"""News feed abstraction — headlines for the fundamental agent.

The default provider uses Alpaca's market-data news endpoint (included with
standard Alpaca data credentials). When news is unavailable the feed returns
an empty list and the fundamental agent falls back to qualitative reasoning.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from alpaca.common.exceptions import APIError
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from aoa.brokerage.base import BrokerError


@dataclass(frozen=True)
class NewsItem:
    headline: str
    summary: str
    source: str
    created_at: str
    symbols: tuple[str, ...] = ()

    def to_context(self) -> dict:
        return {
            "headline": self.headline,
            "summary": self.summary,
            "source": self.source,
            "created_at": self.created_at,
            "symbols": list(self.symbols),
        }


class NewsFeed(ABC):
    @abstractmethod
    def headlines(self, symbols: list[str], *, limit: int = 5) -> dict[str, list[NewsItem]]:
        """Return recent headlines keyed by symbol."""


class NullNewsFeed(NewsFeed):
    """No-op feed — always returns empty lists."""

    def headlines(self, symbols: list[str], *, limit: int = 5) -> dict[str, list[NewsItem]]:
        return {sym.upper(): [] for sym in symbols}


class AlpacaNewsFeed(NewsFeed):
    """Fetch headlines from Alpaca Market Data via ``alpaca-py``."""

    def __init__(self, key_id: str, secret_key: str, *, timeout: float = 20.0) -> None:
        del timeout  # alpaca-py manages HTTP timeouts internally
        if not key_id or not secret_key:
            raise BrokerError("Alpaca credentials are required for the news feed.")
        self._client = NewsClient(api_key=key_id, secret_key=secret_key)

    def close(self) -> None:
        session = getattr(self._client, "_session", None)
        if session is not None:
            session.close()

    def headlines(self, symbols: list[str], *, limit: int = 5) -> dict[str, list[NewsItem]]:
        if not symbols:
            return {}
        by_symbol: dict[str, list[NewsItem]] = {sym.upper(): [] for sym in symbols}
        try:
            news_set = self._client.get_news(
                NewsRequest(
                    symbols=",".join(sym.upper() for sym in symbols),
                    limit=max(limit * len(symbols), limit),
                    sort="desc",
                )
            )
        except APIError:
            return by_symbol

        for article in news_set.data.get("news", []):
            item = _parse_news_row(article.model_dump(mode="json"))
            if item is None:
                continue
            for sym in item.symbols:
                bucket = by_symbol.setdefault(sym.upper(), [])
                if len(bucket) < limit:
                    bucket.append(item)
        return by_symbol


def _parse_news_row(row: dict) -> NewsItem | None:
    headline = (row.get("headline") or "").strip()
    if not headline:
        return None
    summary = (row.get("summary") or row.get("content") or "").strip()
    if len(summary) > 500:
        summary = summary[:497] + "..."
    created = row.get("created_at") or row.get("updated_at") or ""
    if isinstance(created, datetime):
        created = created.isoformat()
    symbols = tuple(
        s.upper()
        for s in (row.get("symbols") or [])
        if isinstance(s, str) and s.strip()
    )
    return NewsItem(
        headline=headline,
        summary=summary,
        source=str(row.get("source") or row.get("author") or "unknown"),
        created_at=str(created),
        symbols=symbols,
    )
