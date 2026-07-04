"""Tests for stock + crypto bar fetching."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from alpaca.common.exceptions import APIError
from requests import Response
from requests.exceptions import HTTPError

from aoa.brokerage.alpaca import AlpacaBroker
from aoa.brokerage.alpaca_bars import (
    AlpacaBarsConfig,
    AlpacaBarsFetcher,
    is_crypto_symbol,
    partition_symbols,
)
from aoa.brokerage.base import BrokerError
from aoa.brokerage.models import Bar


def _api_error(status_code: int) -> APIError:
    response = Response()
    response.status_code = status_code
    return APIError("{}", HTTPError(response=response))


def _sample_bar() -> Bar:
    return Bar(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
    )


def test_is_crypto_symbol():
    assert is_crypto_symbol("BTC/USD") is True
    assert is_crypto_symbol("AAPL") is False


def test_partition_symbols():
    crypto, stocks = partition_symbols(["btc/usd", "AAPL", "ETH/USD"])
    assert crypto == ["BTC/USD", "ETH/USD"]
    assert stocks == ["AAPL"]


def test_fetch_crypto_bars():
    fetcher = AlpacaBarsFetcher()
    bar_set = MagicMock()
    bar_set.data = {"BTC/USD": [_sample_bar()]}
    fetcher._crypto.get_crypto_bars = MagicMock(return_value=bar_set)

    out = fetcher.fetch_crypto(["BTC/USD"], limit=1)

    assert out["BTC/USD"][0].close == 100.5
    fetcher._crypto.get_crypto_bars.assert_called_once()


def test_fetch_stocks_requires_keys():
    fetcher = AlpacaBarsFetcher(AlpacaBarsConfig())
    with pytest.raises(BrokerError, match="Stock bars need Alpaca API keys"):
        fetcher.fetch_stocks(["AAPL"])


def test_fetch_stocks_with_keys():
    fetcher = AlpacaBarsFetcher(AlpacaBarsConfig(key_id="k", secret_key="s"))
    bar_set = MagicMock()
    bar_set.data = {"AAPL": [_sample_bar()]}
    fetcher._stock.get_stock_bars = MagicMock(return_value=bar_set)

    out = fetcher.fetch_stocks(["AAPL"], limit=1)

    assert out["AAPL"][0].close == 100.5


def test_fetch_mixed_symbols():
    fetcher = AlpacaBarsFetcher(AlpacaBarsConfig(key_id="k", secret_key="s"))
    crypto_set = MagicMock()
    crypto_set.data = {"BTC/USD": [_sample_bar()]}
    stock_set = MagicMock()
    stock_set.data = {"AAPL": [_sample_bar()]}
    fetcher._crypto.get_crypto_bars = MagicMock(return_value=crypto_set)
    fetcher._stock.get_stock_bars = MagicMock(return_value=stock_set)

    out = fetcher.fetch(["BTC/USD", "AAPL"], limit=1)

    assert set(out) == {"BTC/USD", "AAPL"}


def test_alpaca_broker_get_crypto_bars_batch():
    broker = AlpacaBroker("key-id", "secret-key")
    bar_set = MagicMock()
    bar_set.data = {"BTC/USD": [_sample_bar()]}
    broker._crypto_data.get_crypto_bars = MagicMock(return_value=bar_set)

    out = broker.get_crypto_bars_batch(["BTC/USD"], "1Day", 1)

    assert out["BTC/USD"][0].close == 100.5


def test_verify_crypto_bars_empty():
    fetcher = AlpacaBarsFetcher()
    bar_set = MagicMock()
    bar_set.data = {"BTC/USD": []}
    fetcher._crypto.get_crypto_bars = MagicMock(return_value=bar_set)

    with pytest.raises(BrokerError, match="returned no data"):
        fetcher.verify_crypto("BTC/USD")
