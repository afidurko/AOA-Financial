"""Tests for Alpaca multi-symbol bars fetching."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from aoa.brokerage.alpaca import AlpacaBroker, _bars_from_rows
from aoa.data.market_data import MarketDataService


def test_bars_from_rows_parses_ohlcv():
    rows = [
        {
            "t": "2024-01-02T05:00:00Z",
            "o": 100.0,
            "h": 101.0,
            "l": 99.5,
            "c": 100.5,
            "v": 12345,
        }
    ]
    bars = _bars_from_rows(rows)
    assert len(bars) == 1
    assert bars[0].close == 100.5
    assert bars[0].timestamp == datetime(2024, 1, 2, 5, 0, tzinfo=timezone.utc)


def test_get_bars_batch_paginates_until_all_symbols_filled():
    broker = AlpacaBroker("key", "secret", live=False)
    responses = [
        {
            "bars": {
                "AAPL": [
                    {
                        "t": "2024-01-01T05:00:00Z",
                        "o": 1,
                        "h": 1,
                        "l": 1,
                        "c": 1,
                        "v": 1,
                    },
                    {
                        "t": "2024-01-02T05:00:00Z",
                        "o": 2,
                        "h": 2,
                        "l": 2,
                        "c": 2,
                        "v": 2,
                    },
                ]
            },
            "next_page_token": "page-2",
        },
        {
            "bars": {
                "MSFT": [
                    {
                        "t": "2024-01-01T05:00:00Z",
                        "o": 10,
                        "h": 10,
                        "l": 10,
                        "c": 10,
                        "v": 10,
                    },
                    {
                        "t": "2024-01-02T05:00:00Z",
                        "o": 11,
                        "h": 11,
                        "l": 11,
                        "c": 11,
                        "v": 11,
                    },
                ]
            },
            "next_page_token": None,
        },
    ]
    broker._data = MagicMock(side_effect=responses)  # type: ignore[method-assign]

    out = broker.get_bars_batch(["AAPL", "MSFT"], limit=2)

    assert len(out["AAPL"]) == 2
    assert out["AAPL"][0].close == 1.0
    assert out["AAPL"][-1].close == 2.0
    assert len(out["MSFT"]) == 2
    assert out["MSFT"][-1].close == 11.0
    assert broker._data.call_count == 2
    first_call = broker._data.call_args_list[0]
    assert first_call.args == ("GET", "/v2/stocks/bars")
    assert first_call.kwargs["params"]["symbols"] == "AAPL,MSFT"
    assert "page_token" not in first_call.kwargs["params"]
    second_call = broker._data.call_args_list[1]
    assert second_call.kwargs["params"]["page_token"] == "page-2"


def test_get_bars_delegates_to_batch_endpoint():
    broker = AlpacaBroker("key", "secret", live=False)
    broker.get_bars_batch = MagicMock(  # type: ignore[method-assign]
        return_value={"AAPL": ["bar1", "bar2"]}
    )

    bars = broker.get_bars("aapl", limit=2)

    broker.get_bars_batch.assert_called_once_with(["aapl"], "1Day", 2)
    assert bars == ["bar1", "bar2"]


def test_market_data_service_uses_batch_bars(fake_broker):
    calls: list[list[str]] = []
    original_batch = fake_broker.get_bars_batch

    def _batch(symbols, timeframe="1Day", limit=120):
        calls.append(list(symbols))
        return original_batch(symbols, timeframe, limit)

    fake_broker.get_bars_batch = _batch  # type: ignore[method-assign]
    svc = MarketDataService(fake_broker, bar_limit=30)

    snaps = svc.snapshots(["AAPL", "MSFT", "NVDA"])

    assert set(snaps) == {"AAPL", "MSFT", "NVDA"}
    assert len(calls) == 1
    assert set(calls[0]) == {"AAPL", "MSFT", "NVDA"}
    assert all(len(snaps[s].bars) == 30 for s in snaps)
