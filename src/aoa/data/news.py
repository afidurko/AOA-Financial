"""News feed abstraction — headlines for the fundamental agent.

Providers:
- ``AlpacaNewsFeed`` — Alpaca market-data news (when ``AOA_BROKER=alpaca``)
- ``MoomooNewsFeed`` — OpenD ``get_search_news`` (moomooapi skill; default broker)
- ``NullNewsFeed`` — empty headlines when news is disabled or unreachable
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

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

    def clear_cache(self) -> None:
        """No-op unless a concrete feed caches per-cycle results."""
        return None


class NullNewsFeed(NewsFeed):
    """No-op feed — always returns empty lists."""

    def headlines(self, symbols: list[str], *, limit: int = 5) -> dict[str, list[NewsItem]]:
        return {sym.upper(): [] for sym in symbols}


class AlpacaNewsFeed(NewsFeed):
    """Fetch headlines from Alpaca Market Data via ``alpaca-py``."""

    def __init__(
        self,
        key_id: str = "",
        secret_key: str = "",
        *,
        oauth_token: str = "",
        lookback_hours: int = 72,
        timeout: float = 20.0,
    ) -> None:
        del timeout  # alpaca-py manages HTTP timeouts internally
        has_oauth = bool(oauth_token)
        has_keys = bool(key_id and secret_key)
        if not has_oauth and not has_keys:
            raise BrokerError("Alpaca credentials are required for the news feed.")
        self.lookback_hours = lookback_hours
        if has_oauth:
            self._client = NewsClient(oauth_token=oauth_token)
        else:
            self._client = NewsClient(api_key=key_id, secret_key=secret_key)
        self._cache: dict[str, list[NewsItem]] = {}

    def close(self) -> None:
        session = getattr(self._client, "_session", None)
        if session is not None:
            session.close()

    def clear_cache(self) -> None:
        self._cache.clear()

    def headlines(self, symbols: list[str], *, limit: int = 5) -> dict[str, list[NewsItem]]:
        if not symbols:
            return {}
        normalized = [s.upper() for s in symbols if s]
        missing = [s for s in normalized if s not in self._cache]
        if missing:
            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=self.lookback_hours)
            try:
                news_set = self._client.get_news(
                    NewsRequest(
                        symbols=",".join(missing),
                        start=start,
                        end=end,
                        limit=max(50, limit * len(missing)),
                        sort="desc",
                    )
                )
            except APIError:
                for sym in missing:
                    self._cache[sym] = []
            else:
                grouped: dict[str, list[NewsItem]] = {sym: [] for sym in missing}
                for article in news_set.data.get("news", []):
                    item = _parse_news_row(article.model_dump(mode="json"))
                    if item is None:
                        continue
                    for sym in item.symbols:
                        if sym in grouped and len(grouped[sym]) < limit:
                            grouped[sym].append(item)
                for sym in missing:
                    self._cache[sym] = grouped[sym]
        return {s: list(self._cache.get(s, [])) for s in normalized}


class MoomooNewsFeed(NewsFeed):
    """Fetch headlines via OpenD ``get_search_news`` (moomooapi skill)."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        connect_timeout: float = 3.0,
    ) -> None:
        from aoa.brokerage.moomoo import probe_opend

        self._host = host
        self._port = int(port)
        self._connect_timeout = float(connect_timeout)
        self._cache: dict[str, list[NewsItem]] = {}
        probe_opend(self._host, self._port, timeout=self._connect_timeout)

    def clear_cache(self) -> None:
        self._cache.clear()

    def headlines(self, symbols: list[str], *, limit: int = 5) -> dict[str, list[NewsItem]]:
        if not symbols:
            return {}
        try:
            import moomoo as ft
        except ImportError as exc:  # pragma: no cover
            raise BrokerError("moomoo-api is not installed. Run: pip install moomoo-api") from exc

        normalized = [s.upper() for s in symbols if s]
        missing = [s for s in normalized if s not in self._cache]
        if not missing:
            return {s: list(self._cache.get(s, [])) for s in normalized}

        news_sub = getattr(getattr(ft, "NewsSubType", None), "NEWS", "NEWS")
        ctx = ft.OpenQuoteContext(host=self._host, port=self._port)
        try:
            for sym in missing:
                self._cache[sym] = self._fetch_symbol(ctx, ft, sym, limit=limit, news_sub=news_sub)
        finally:
            close = getattr(ctx, "close", None)
            if callable(close):
                close()
        return {s: list(self._cache.get(s, [])) for s in normalized}

    @staticmethod
    def _fetch_symbol(ctx: Any, ft: Any, sym: str, *, limit: int, news_sub: Any) -> list[NewsItem]:
        try:
            ret, data = ctx.get_search_news(sym, max(1, min(limit, 100)), news_sub_type=news_sub)
            if ret != ft.RET_OK or data is None or len(data) == 0:
                return []
            items: list[NewsItem] = []
            for _, row in data.iterrows():
                item = _parse_moomoo_news_row(row, default_symbol=sym)
                if item is not None:
                    items.append(item)
                if len(items) >= limit:
                    break
            return items
        except Exception:  # noqa: BLE001 — per-symbol soft fail
            return []


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


def _parse_moomoo_news_row(row: Any, *, default_symbol: str) -> NewsItem | None:
    """Map moomooapi ``get_search_news`` fields → ``NewsItem``."""
    from aoa.brokerage.moomoo import _row_value

    headline = str(_row_value(row, "title", "") or _row_value(row, "headline", "")).strip()
    if not headline:
        return None
    summary = str(_row_value(row, "content", "") or _row_value(row, "summary", "")).strip()
    if len(summary) > 500:
        summary = summary[:497] + "..."
    created = _row_value(row, "publish_time", "") or _row_value(row, "created_at", "")
    if isinstance(created, datetime):
        created = created.isoformat()
    symbols = _related_symbols(_row_value(row, "related_securities", None), default_symbol)
    return NewsItem(
        headline=headline,
        summary=summary,
        source=str(_row_value(row, "source", "") or "moomoo"),
        created_at=str(created),
        symbols=tuple(symbols),
    )


def _related_symbols(related: Any, default_symbol: str) -> list[str]:
    symbols: list[str] = []
    parts: list[Any]
    if isinstance(related, str) and related.strip():
        parts = related.replace(";", ",").split(",")
    elif isinstance(related, (list, tuple)):
        parts = list(related)
    else:
        parts = []
    for part in parts:
        token = str(part).strip().upper()
        if "." in token:
            token = token.split(".", 1)[1]
        if token:
            symbols.append(token)
    return symbols or [default_symbol.upper()]
