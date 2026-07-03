"""Tests for Alpaca multi-symbol bars fetching."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from aoa.brokerage.alpaca import AlpacaBroker, _bars_from_rows
from aoa.brokerage.base import BrokerError
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


def test_get_bars_batch_passes_feed_and_adjustment():
    broker = AlpacaBroker(
        "key",
        "secret",
        live=False,
        data_feed="sip",
        bar_adjustment="raw",
    )
    broker._data = MagicMock(  # type: ignore[method-assign]
        return_value={"bars": {"AAPL": []}, "next_page_token": None}
    )

    broker.get_bars_batch(["AAPL"], limit=10)

    params = broker._data.call_args.kwargs["params"]
    assert params["feed"] == "sip"
    assert params["adjustment"] == "raw"
    assert params["symbols"] == "AAPL"
    assert params["timeframe"] == "1Day"


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


def test_api_error_401_includes_trading_key_hint():
    broker = AlpacaBroker("key", "secret", live=False)
    err = broker._api_error(
        "GET",
        "https://data.alpaca.markets/v2/stocks/bars",
        401,
        "unauthorized",
    )
    assert "PK..." in str(err)
    assert "authx.alpaca.markets" in str(err)


def test_invalid_data_feed_rejected_at_init():
    try:
        AlpacaBroker("key", "secret", live=False, data_feed="not-a-feed")
    except BrokerError as exc:
        assert "Invalid Alpaca data feed" in str(exc)
    else:
        raise AssertionError("expected BrokerError")


def test_request_rejects_non_json_response():
    broker = AlpacaBroker("key", "secret", live=False)
    response = MagicMock()
    response.status_code = 200
    response.content = b"not-json"
    response.text = "not-json"
    response.json.side_effect = ValueError("bad json")
    broker._client.request = MagicMock(return_value=response)  # type: ignore[method-assign]

    try:
        broker._request("GET", "https://data.alpaca.markets/v2/stocks/bars")
    except BrokerError as exc:
        assert "non-JSON" in str(exc)
    else:
        raise AssertionError("expected BrokerError")
