"""Tests for the Alpaca news feed parser and integration."""

from __future__ import annotations

from aoa.agents.fundamental import FundamentalAgent
from aoa.brokerage.models import Quote
from aoa.data.market_data import SymbolSnapshot
from aoa.data.news import AlpacaNewsFeed, NewsItem, NullNewsFeed, _parse_news_row


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


def test_fundamental_agent_with_headlines(fake_llm):
    agent = FundamentalAgent(fake_llm)
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99, ask=101),
        technicals={"last_close": 100.0},
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


def test_alpaca_news_feed_handles_http_error(monkeypatch):
    import httpx

    class FakeClient:
        def get(self, *args, **kwargs):
            raise httpx.HTTPError("network down")

        def close(self):
            pass

    monkeypatch.setattr("aoa.data.news.httpx.Client", lambda **kw: FakeClient())
    feed = AlpacaNewsFeed("key", "secret")
    result = feed.headlines(["AAPL"])
    assert result == {"AAPL": []}
