"""Tests for Alpaca news wiring and volume metrics."""

from __future__ import annotations

from datetime import datetime, timezone

from aoa.brokerage.models import NewsItem
from aoa.data import indicators
from aoa.data.news import NewsService
from tests.conftest import FakeBroker


def test_volume_metrics_ratio():
    from datetime import timedelta

    from aoa.brokerage.models import Bar

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
    from datetime import timedelta

    from aoa.brokerage.models import Bar

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


def test_news_service_groups_by_symbol():
    broker = FakeBroker()

    class MultiNewsBroker(FakeBroker):
        def get_news(self, symbols, *, limit=50, lookback_hours=72):
            return [
                NewsItem(
                    headline="AAPL launches new product",
                    summary="Product launch.",
                    source="benzinga",
                    symbols=("AAPL", "MSFT"),
                    published_at=datetime.now(timezone.utc),
                ),
                NewsItem(
                    headline="NVDA data-center demand rises",
                    summary="Demand story.",
                    source="benzinga",
                    symbols=("NVDA",),
                    published_at=datetime.now(timezone.utc),
                ),
            ]

    svc = NewsService(MultiNewsBroker(), limit_per_symbol=2)
    grouped = svc.fetch(["AAPL", "NVDA"])
    assert len(grouped["AAPL"]) == 1
    assert grouped["AAPL"][0].headline.startswith("AAPL")
    assert len(grouped["NVDA"]) == 1
