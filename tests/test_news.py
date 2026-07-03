"""Tests for Alpaca news feed, volume metrics, and fundamental integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from aoa.agents.fundamental import FundamentalAgent
from aoa.brokerage.models import Bar, Quote
from aoa.data import indicators
from aoa.data.market_data import SymbolSnapshot
from aoa.data.news import AlpacaNewsFeed, NewsItem, NullNewsFeed, _parse_news_row


def test_volume_metrics_ratio():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [
        Bar(
            timestamp=base + timedelta(days=i),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1_000_000 if i < 19 else 2_000_000,
        )
        for i in range(20)
    ]
    m = indicators.volume_metrics(bars)
    assert m["latest_volume"] == 2_000_000
    assert m["avg_volume_20d"] == 1_050_000
    assert m["volume_ratio"] == 1.9


def test_technical_snapshot_includes_volume():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [
        Bar(
            timestamp=base + timedelta(days=i),
            open=float(i),
            high=float(i),
            low=float(i),
            close=float(i),
            volume=1000 + i,
        )
        for i in range(30)
    ]
    snap = indicators.technical_snapshot(bars)
    assert "volume" in snap
    assert snap["volume"]["latest_volume"] is not None


def test_parse_news_row():
    row = {
        "headline": "Apple beats estimates",
        "summary": "Strong iPhone sales.",
        "source": "Reuters",
        "created_at": "2025-01-15T14:00:00Z",
        "symbols": ["AAPL"],
    }
    item = _parse_news_row(row)
    assert item is not None
    assert item.headline == "Apple beats estimates"
    assert item.symbols == ("AAPL",)


def test_null_news_feed():
    feed = NullNewsFeed()
    result = feed.headlines(["AAPL", "MSFT"], limit=3)
    assert result == {"AAPL": [], "MSFT": []}


def test_alpaca_news_feed_groups_by_symbol(monkeypatch):
    article_aapl = MagicMock()
    article_aapl.model_dump.return_value = {
        "headline": "AAPL launches new product",
        "summary": "Product launch.",
        "source": "benzinga",
        "created_at": "2025-01-01T12:00:00Z",
        "symbols": ["AAPL", "MSFT"],
    }
    article_nvda = MagicMock()
    article_nvda.model_dump.return_value = {
        "headline": "NVDA data-center demand rises",
        "summary": "Demand story.",
        "source": "benzinga",
        "created_at": "2025-01-01T11:00:00Z",
        "symbols": ["NVDA"],
    }
    news_set = MagicMock()
    news_set.data = {"news": [article_aapl, article_nvda]}

    class FakeClient:
        def get_news(self, *args, **kwargs):
            return news_set

        def close(self):
            pass

    monkeypatch.setattr("aoa.data.news.NewsClient", lambda **kw: FakeClient())
    feed = AlpacaNewsFeed("key", "secret")
    grouped = feed.headlines(["AAPL", "NVDA"], limit=2)
    assert len(grouped["AAPL"]) == 1
    assert grouped["AAPL"][0].headline.startswith("AAPL")
    assert len(grouped["NVDA"]) == 1


def test_fundamental_agent_with_headlines(fake_llm):
    agent = FundamentalAgent(fake_llm)
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99, ask=101),
        technicals={"1Day": {"last_close": 100.0}},
    )
    headlines = [
        NewsItem(
            headline="Test headline",
            summary="Test summary",
            source="test",
            created_at="2025-01-01",
            symbols=("AAPL",),
        )
    ]
    signal = agent.analyze(snap, headlines=headlines)
    assert signal.symbol == "AAPL"
    assert signal.source == "fundamental"


def test_alpaca_news_feed_handles_api_error(monkeypatch):
    from alpaca.common.exceptions import APIError

    class FakeClient:
        def get_news(self, *args, **kwargs):
            raise APIError('{"message":"forbidden"}')

        def close(self):
            pass

    monkeypatch.setattr("aoa.data.news.NewsClient", lambda **kw: FakeClient())
    feed = AlpacaNewsFeed("key", "secret")
    result = feed.headlines(["AAPL"])
    assert result == {"AAPL": []}
