"""Tests for Alpaca historical bars and batch market-data fetching."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from aoa.brokerage.alpaca import AlpacaBroker, _bar_from_sdk
from aoa.data.market_data import MarketDataService
from aoa.data.timeframes import TimeframeSpec, parse_timeframes
from conftest import FakeBroker


def test_bar_from_sdk_parses_row():
    row = MagicMock()
    row.timestamp = datetime(2022, 1, 3, 9, 0, tzinfo=timezone.utc)
    row.open = 178.26
    row.high = 178.34
    row.low = 177.76
    row.close = 178.08
    row.volume = 60937
    bar = _bar_from_sdk(row)
    assert bar.open == 178.26
    assert bar.close == 178.08
    assert bar.volume == 60937


def test_market_data_service_batches_bar_requests():
    calls: list[tuple[list[str], str, int]] = []

    class TrackingBroker(FakeBroker):
        def get_bars_batch(self, symbols, timeframe="1Day", limit=120):
            calls.append((list(symbols), timeframe, limit))
            return super().get_bars_batch(symbols, timeframe, limit)

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


def test_alpaca_broker_get_bars_batch():
    broker = AlpacaBroker("key-id", "secret-key")
    bar_set = MagicMock()
    bar_set.data = {
        "AAPL": [
            MagicMock(
                timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000.0,
            )
        ],
        "MSFT": [
            MagicMock(
                timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
                open=200.0,
                high=201.0,
                low=199.0,
                close=200.5,
                volume=2000.0,
            )
        ],
    }
    broker._stock_data.get_stock_bars = MagicMock(return_value=bar_set)

    result = broker.get_bars_batch(["AAPL", "MSFT"], "1Day", 1)

    assert set(result.keys()) == {"AAPL", "MSFT"}
    assert result["AAPL"][0].close == 100.5
