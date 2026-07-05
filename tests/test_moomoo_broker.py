"""Tests for Moomoo broker adapter (mocked SDK)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from aoa.brokerage.base import BrokerError
from aoa.brokerage.models import OrderRequest, Side
from aoa.brokerage.moomoo import MoomooBroker
from aoa.brokerage.moomoo_symbols import from_moomoo_code, to_moomoo_code
from aoa.config import Config


def test_symbol_mapping():
    assert to_moomoo_code("aapl") == "US.AAPL"
    assert from_moomoo_code("US.AAPL") == "AAPL"


def _fake_ft_module():
    ft = MagicMock()
    ft.RET_OK = 0
    ft.TrdEnv.SIMULATE = "SIMULATE"
    ft.TrdEnv.REAL = "REAL"
    ft.SecurityFirm.FUTUINC = "FUTUINC"
    ft.TrdMarket.US = "US"
    ft.TrdSide.BUY = "BUY"
    ft.TrdSide.SELL = "SELL"
    ft.OrderType.MARKET = "MARKET"
    ft.TimeInForce.DAY = "DAY"
    ft.KLType.K_DAY = "K_DAY"
    ft.MarketState.AFTERNOON = "AFTERNOON"
    ft.ModifyOrderOp.CANCEL = "CANCEL"
    return ft


@patch("aoa.brokerage.moomoo.MoomooBroker._sdk")
def test_get_account(mock_sdk):
    ft = _fake_ft_module()
    mock_sdk.return_value = ft
    trade = MagicMock()
    trade.accinfo_query.return_value = (
        0,
        pd.DataFrame([{"cash": 10000, "total_assets": 12000, "power": 10000, "currency": "USD"}]),
    )
    broker = MoomooBroker(trd_env="SIMULATE")
    broker._trade_ctx = trade
    acct = broker.get_account()
    assert acct.equity == 12000
    assert acct.cash == 10000


@patch("aoa.brokerage.moomoo.MoomooBroker._sdk")
def test_get_quote(mock_sdk):
    ft = _fake_ft_module()
    mock_sdk.return_value = ft
    quote = MagicMock()
    quote.get_market_snapshot.return_value = (
        0,
        pd.DataFrame(
            [{"code": "US.AAPL", "bid_price": 100.0, "ask_price": 100.1, "bid_vol": 1, "ask_vol": 2}]
        ),
    )
    broker = MoomooBroker()
    broker._quote_ctx = quote
    q = broker.get_quote("AAPL")
    assert q.symbol == "AAPL"
    assert q.bid == 100.0


def test_build_broker_moomoo():
    cfg = Config(
        broker="moomoo",
        anthropic_api_key="x",
        moomoo_opend_host="127.0.0.1",
        moomoo_opend_port=11111,
        moomoo_trd_env="SIMULATE",
    )
    from aoa.cli import build_broker

    broker = build_broker(cfg)
    assert broker.name == "moomoo-simulate"


def test_protected_order_rejected():
    broker = MoomooBroker()
    req = OrderRequest(
        symbol="AAPL",
        qty=1,
        side=Side.BUY,
        stop_loss_price=90.0,
    )
    with pytest.raises(BrokerError, match="bracket"):
        broker.submit_order(req)
