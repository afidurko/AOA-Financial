"""Tests for Alpaca broker market-data access."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from aoa.brokerage.alpaca import AlpacaBroker
from aoa.brokerage.base import BrokerError
from aoa.cli import cmd_doctor
from aoa.config import Config


def _bars_payload() -> dict:
    return {
        "bars": [
            {
                "t": "2024-01-02T00:00:00Z",
                "o": 100.0,
                "h": 101.0,
                "l": 99.0,
                "c": 100.5,
                "v": 1000,
            }
        ]
    }


def _ok_response(payload: dict | list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = b"{}"
    resp.json.return_value = payload
    return resp


def test_verify_stock_bars_success():
    broker = AlpacaBroker("key-id", "secret-key")
    broker._client.request = MagicMock(return_value=_ok_response(_bars_payload()))

    bar = broker.verify_stock_bars("AAPL", limit=1)

    assert bar.close == 100.5
    assert bar.timestamp == datetime(2024, 1, 2, tzinfo=timezone.utc)
    call = broker._client.request.call_args
    assert call.args[0] == "GET"
    assert call.args[1] == "https://data.alpaca.markets/v2/stocks/AAPL/bars"
    assert call.kwargs["params"]["limit"] == 1


def test_verify_stock_bars_auth_failure():
    resp = MagicMock()
    resp.status_code = 403
    resp.text = '{"message":"forbidden"}'
    broker = AlpacaBroker("bad-key", "bad-secret")
    broker._client.request = MagicMock(return_value=resp)

    with pytest.raises(BrokerError, match="403"):
        broker.verify_stock_bars("AAPL")


def test_verify_stock_bars_empty_response():
    broker = AlpacaBroker("key-id", "secret-key")
    broker._client.request = MagicMock(return_value=_ok_response({"bars": []}))

    with pytest.raises(BrokerError, match="returned no data"):
        broker.verify_stock_bars("AAPL")


def test_cmd_doctor_reports_stock_bars_check(monkeypatch):
    cfg = Config(anthropic_api_key="x", alpaca_key_id="k", alpaca_secret_key="s")
    broker = MagicMock()
    broker.name = "alpaca-paper"
    broker.get_account.return_value.equity = 50_000.0
    broker.is_market_open.return_value = True
    broker.verify_stock_bars.return_value.timestamp = datetime(
        2024, 1, 2, tzinfo=timezone.utc
    )
    broker.verify_stock_bars.return_value.close = 190.12
    monkeypatch.setattr("aoa.cli.build_broker", lambda _cfg: broker)
    monkeypatch.setattr("aoa.cli.build_llm", lambda _cfg: MagicMock())

    assert cmd_doctor(cfg) == 0
    broker.verify_stock_bars.assert_called_once_with("AAPL", limit=1)
