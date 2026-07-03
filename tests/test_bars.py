"""Tests for Alpaca historical bars parsing and batch market-data fetching."""

from __future__ import annotations

from datetime import datetime, timezone

from aoa.brokerage.alpaca import bar_from_row
from aoa.brokerage.models import Bar
from aoa.data.market_data import MarketDataService
from aoa.data.timeframes import TimeframeSpec, parse_timeframes
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
    calls: list[tuple[list[str], str, int]] = []

    class TrackingBroker(FakeBroker):
        def get_bars_many(self, symbols, timeframe="1Day", limit=120, *, feed=None):
            calls.append((list(symbols), timeframe, limit))
            return super().get_bars_many(symbols, timeframe, limit, feed=feed)

    broker = TrackingBroker()
    daily = (TimeframeSpec("1Day", "1Day", 30),)
    svc = MarketDataService(broker, timeframes=daily)
    snaps = svc.snapshots(["AAPL", "MSFT", "NVDA"])

    assert len(snaps) == 3
    assert len(calls) == 1
    assert set(calls[0][0]) == {"AAPL", "MSFT", "NVDA"}
    assert calls[0][1] == "1Day"
    assert calls[0][2] == 30
    assert all(len(snaps[s].bars) == 30 for s in snaps)


def test_default_timeframe_stack():
    specs = parse_timeframes("")
    keys = [s.key for s in specs]
    assert keys == ["1Min", "3Min", "5Min", "15Min", "1Hour", "1Day", "12Month"]


def test_parse_timeframes_accepts_aliases():
    specs = parse_timeframes("1D,1H,1Year")
    assert [s.key for s in specs] == ["1Day", "1Hour", "12Month"]


def test_multi_timeframe_snapshot_structure():
    tfs = (
        TimeframeSpec("5Min", "5Min", 20),
        TimeframeSpec("1Day", "1Day", 20),
    )
    svc = MarketDataService(FakeBroker(), timeframes=tfs)
    snap = svc.snapshot("AAPL")
    assert set(snap.bars_by_timeframe.keys()) == {"5Min", "1Day"}
    assert set(snap.technicals.keys()) == {"5Min", "1Day"}
    assert snap.last_close() == snap.technicals["1Day"]["last_close"]
    ctx = snap.to_context()
    assert ctx["primary_timeframe"] == "1Day"
    assert "5Min" in ctx["technicals"]
