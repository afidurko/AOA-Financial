"""Tests for Alpaca broker market-data access."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from alpaca.common.exceptions import APIError
from requests import Response
from requests.exceptions import HTTPError

from aoa.brokerage.alpaca import AlpacaBroker, _settled_cash_from_alpaca
from aoa.brokerage.base import BrokerError
from aoa.brokerage.models import Bar
from aoa.cli import cmd_doctor
from aoa.config import Config


def _api_error(status_code: int, body: str = '{"message":"forbidden"}') -> APIError:
    response = Response()
    response.status_code = status_code
    return APIError(body, HTTPError(response=response))


def _sample_bar() -> Bar:
    return Bar(
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
    )


def test_settled_cash_uses_non_marginable_buying_power():
    acct = MagicMock()
    acct.cash = "10000"
    acct.non_marginable_buying_power = "7500"
    assert _settled_cash_from_alpaca(acct) == 7500.0


def test_settled_cash_falls_back_to_cash():
    acct = MagicMock()
    acct.cash = "5000"
    acct.non_marginable_buying_power = None
    acct.cash_withdrawable = None
    assert _settled_cash_from_alpaca(acct) == 5000.0


def test_get_account_maps_settled_cash():
    broker = AlpacaBroker("key-id", "secret-key")
    acct = MagicMock()
    acct.equity = "100000"
    acct.cash = "40000"
    acct.buying_power = "80000"
    acct.non_marginable_buying_power = "25000"
    acct.options_approved_level = 2
    acct.daytrade_count = 0
    acct.pattern_day_trader = False
    acct.currency = "USD"
    broker._trading.get_account = MagicMock(return_value=acct)

    account = broker.get_account()

    assert account.settled_cash == 25000.0
    assert account.cash == 40000.0


def test_verify_stock_bars_success():
    broker = AlpacaBroker("key-id", "secret-key")
    bar_set = MagicMock()
    bar_set.data = {"AAPL": [_sample_bar()]}
    broker._stock_data.get_stock_bars = MagicMock(return_value=bar_set)

    bar = broker.verify_stock_bars("AAPL", limit=1)

    assert bar.close == 100.5
    assert bar.timestamp == datetime(2024, 1, 2, tzinfo=timezone.utc)
    broker._stock_data.get_stock_bars.assert_called_once()
    request = broker._stock_data.get_stock_bars.call_args.args[0]
    assert request.symbol_or_symbols == ["AAPL"]
    assert request.limit == 1


def test_verify_stock_bars_auth_failure():
    broker = AlpacaBroker("bad-key", "bad-secret")
    broker._stock_data.get_stock_bars = MagicMock(side_effect=_api_error(403))

    with pytest.raises(BrokerError, match="403"):
        broker.verify_stock_bars("AAPL")


def test_verify_stock_bars_empty_response():
    broker = AlpacaBroker("key-id", "secret-key")
    bar_set = MagicMock()
    bar_set.data = {"AAPL": []}
    broker._stock_data.get_stock_bars = MagicMock(return_value=bar_set)

    with pytest.raises(BrokerError, match="returned no data"):
        broker.verify_stock_bars("AAPL")


def test_cmd_doctor_reports_stock_bars_check(monkeypatch):
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        alpaca_data_feed="iex",
        alpaca_bar_adjustment="raw",
    )
    broker = MagicMock()
    broker.name = "alpaca-paper"
    broker.get_account.return_value.equity = 50_000.0
    broker.is_market_open.return_value = True
    broker.verify_stock_bars.return_value = _sample_bar()
    fetcher = MagicMock()
    fetcher.verify_crypto.return_value = _sample_bar()
    monkeypatch.setattr("aoa.cli.AlpacaBarsFetcher", lambda _cfg: fetcher)
    monkeypatch.setattr("aoa.cli.build_broker", lambda _cfg: broker)
    monkeypatch.setattr("aoa.cli.build_llm", lambda _cfg: MagicMock())

    assert cmd_doctor(cfg) == 0
    fetcher.verify_crypto.assert_called_once_with("BTC/USD", limit=1)
    fetcher.close.assert_called_once()
    broker.verify_stock_bars.assert_called_once_with("SPY", limit=1)
