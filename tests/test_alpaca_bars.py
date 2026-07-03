"""Tests for Alpaca multi-symbol bars fetching."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed
from requests import Response
from requests.exceptions import HTTPError

from aoa.brokerage.alpaca import AlpacaBroker, _bars_from_sdk_rows, _sdk_error_message
from aoa.brokerage.base import BrokerError
from aoa.data.market_data import MarketDataService
from aoa.data.timeframes import TimeframeSpec


def _api_error(status_code: int, body: str = '{"message":"unauthorized"}') -> APIError:
    response = Response()
    response.status_code = status_code
    return APIError(body, HTTPError(response=response))


def _sdk_bar(close: float = 100.5) -> MagicMock:
    row = MagicMock()
    row.timestamp = datetime(2024, 1, 2, 5, 0, tzinfo=timezone.utc)
    row.open = close - 0.5
    row.high = close + 0.5
    row.low = close - 1.0
    row.close = close
    row.volume = 12345
    return row


def test_bars_from_sdk_rows_parses_ohlcv():
    bars = _bars_from_sdk_rows([_sdk_bar(100.5)])
    assert len(bars) == 1
    assert bars[0].close == 100.5
    assert bars[0].timestamp == datetime(2024, 1, 2, 5, 0, tzinfo=timezone.utc)


def test_get_bars_batch_fetches_multiple_symbols():
    broker = AlpacaBroker("key", "secret", live=False)
    bar_set = MagicMock()
    bar_set.data = {
        "AAPL": [_sdk_bar(1.0), _sdk_bar(2.0)],
        "MSFT": [_sdk_bar(10.0), _sdk_bar(11.0)],
    }
    broker._stock_data.get_stock_bars = MagicMock(return_value=bar_set)

    out = broker.get_bars_batch(["AAPL", "MSFT"], limit=2)

    assert len(out["AAPL"]) == 2
    assert out["AAPL"][-1].close == 2.0
    assert len(out["MSFT"]) == 2
    assert out["MSFT"][-1].close == 11.0
    request = broker._stock_data.get_stock_bars.call_args.args[0]
    assert request.symbol_or_symbols == ["AAPL", "MSFT"]
    assert request.limit == 2


def test_get_bars_delegates_to_batch():
    broker = AlpacaBroker("key", "secret", live=False)
    broker.get_bars_batch = MagicMock(return_value={"AAPL": ["bar1", "bar2"]})  # type: ignore[method-assign]

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
    bar_set = MagicMock()
    bar_set.data = {"AAPL": [_sdk_bar()]}
    broker._stock_data.get_stock_bars = MagicMock(return_value=bar_set)

    broker.get_bars_batch(["AAPL"], limit=10)

    request = broker._stock_data.get_stock_bars.call_args.args[0]
    assert request.feed is DataFeed.SIP
    assert request.adjustment is Adjustment.RAW
    assert request.symbol_or_symbols == ["AAPL"]


def test_market_data_service_uses_batch_bars(fake_broker):
    calls: list[list[str]] = []
    original_batch = fake_broker.get_bars_batch

    def _batch(symbols, timeframe="1Day", limit=120):
        calls.append(list(symbols))
        return original_batch(symbols, timeframe, limit)

    fake_broker.get_bars_batch = _batch  # type: ignore[method-assign]
    daily = (TimeframeSpec("1Day", "1Day", 30),)
    svc = MarketDataService(fake_broker, timeframes=daily)

    snaps = svc.snapshots(["AAPL", "MSFT", "NVDA"])

    assert set(snaps) == {"AAPL", "MSFT", "NVDA"}
    assert len(calls) == 1
    assert set(calls[0]) == {"AAPL", "MSFT", "NVDA"}
    assert all(len(snaps[s].bars) == 30 for s in snaps)


def test_sdk_error_message_401_includes_trading_key_hint():
    msg = _sdk_error_message(_api_error(401))
    assert "PK..." in msg
    assert "authx.alpaca.markets" in msg


def test_invalid_data_feed_rejected_at_init():
    try:
        AlpacaBroker("key", "secret", live=False, data_feed="not-a-feed")
    except BrokerError as exc:
        assert "Invalid Alpaca data feed" in str(exc)
    else:
        raise AssertionError("expected BrokerError")
