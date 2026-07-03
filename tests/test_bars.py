"""Tests for Alpaca historical bars parsing and batch market-data fetching."""

from __future__ import annotations

from datetime import datetime, timezone

from aoa.brokerage.alpaca import bar_from_row
from aoa.brokerage.models import Bar
from aoa.data.market_data import MarketDataService
from tests.conftest import FakeBroker


def test_bar_from_row_parses_alpaca_payload():
    bar = bar_from_row(
        {
            "t": "2022-01-03T09:00:00Z",
            "o": 178.26,
            "h": 178.34,
            "l": 177.76,
            "c": 178.08,
            "v": 60937,
            "n": 1727,
            "vw": 177.954244,
        }
    )
    assert bar is not None
    assert bar.open == 178.26
    assert bar.close == 178.08
    assert bar.volume == 60937
    assert bar.timestamp == datetime(2022, 1, 3, 9, 0, tzinfo=timezone.utc)


def test_market_data_service_batches_bar_requests():
    calls: list[list[str]] = []

    class TrackingBroker(FakeBroker):
        def get_bars_many(self, symbols, timeframe="1Day", limit=120):
            calls.append(list(symbols))
            return super().get_bars_many(symbols, timeframe, limit)

    broker = TrackingBroker()
    svc = MarketDataService(broker, bar_limit=30)
    snaps = svc.snapshots(["AAPL", "MSFT", "NVDA"])

    assert len(snaps) == 3
    assert len(calls) == 1
    assert set(calls[0]) == {"AAPL", "MSFT", "NVDA"}
    assert all(len(snaps[s].bars) == 30 for s in snaps)
