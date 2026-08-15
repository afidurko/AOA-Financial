"""Tests for Moomoo symbol helpers and skill-aligned field parsing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aoa.brokerage.base import BrokerError
from aoa.brokerage.models import AssetClass, OrderRequest, OrderType, Side
from aoa.brokerage.moomoo import (
    MoomooBroker,
    _first_book_level,
    _parse_moomoo_option,
    _parse_option_tail,
    _position_avg_cost,
    _position_unrealized_pl,
    _snapshot_price,
    from_moomoo_code,
    probe_opend,
    to_moomoo_code,
)
from aoa.data.news import _parse_moomoo_news_row


def test_to_moomoo_code_us():
    assert to_moomoo_code("aapl") == "US.AAPL"
    assert to_moomoo_code("US.MSFT") == "US.MSFT"


def test_from_moomoo_code():
    assert from_moomoo_code("US.NVDA") == "NVDA"


def test_first_book_level_list_and_scalar():
    assert _first_book_level([12.5, 11.0]) == 12.5
    assert _first_book_level(9) == 9.0
    assert _first_book_level([]) == 0.0
    assert _first_book_level(None) == 0.0


def test_get_quotes_many_maps_bid_ask_sizes():
    import pandas as pd

    from aoa.brokerage.moomoo import MoomooBroker

    class FakeCtx:
        def get_market_snapshot(self, codes):
            df = pd.DataFrame(
                [
                    {
                        "code": "US.AAPL",
                        "bid_price": [100.0, 99.9],
                        "ask_price": [100.1, 100.2],
                        "bid_vol": [500, 200],
                        "ask_vol": [300, 100],
                        "last_price": 100.05,
                        "update_time": "2024-01-02 15:00:00",
                    }
                ]
            )
            return 0, df

    broker = MoomooBroker.__new__(MoomooBroker)
    broker._market = "US"
    broker._quote_ctx = FakeCtx()
    quote = broker.get_quotes_many(["AAPL"])["AAPL"]
    assert quote.bid == 100.0
    assert quote.ask == 100.1
    assert quote.bid_size == 500.0
    assert quote.ask_size == 300.0


def test_parse_option_tail():
    parsed = _parse_option_tail("250117C00150000")
    assert parsed is not None
    otype, strike, expiry = parsed
    assert otype.value == "call"
    assert strike == 150.0
    assert expiry == "2025-01-17"


def test_parse_moomoo_option_code():
    parsed = _parse_moomoo_option("US.AAPL250117C00150000", "AAPL")
    assert parsed is not None
    _, strike, expiry = parsed
    assert strike == 150.0
    assert expiry == "2025-01-17"


def test_probe_opend_raises_when_unreachable():
    with pytest.raises(BrokerError, match="unreachable"):
        probe_opend("127.0.0.1", 1, timeout=0.5)


def test_snapshot_price_scalar_and_list():
    assert _snapshot_price({"bid_price": 10.5}, "bid_price") == 10.5
    assert _snapshot_price({"bid_price": [11.0, 10.9]}, "bid_price") == 11.0
    assert _snapshot_price({}, "bid_price") == 0.0


def test_position_fields_prefer_average_cost():
    row = {"average_cost": 100.0, "cost_price": 80.0, "unrealized_pl": 5.0, "pl_val": 99.0}
    assert _position_avg_cost(row) == 100.0
    assert _position_unrealized_pl(row) == 5.0
    legacy = {"cost_price": 80.0, "pl_val": 12.0}
    assert _position_avg_cost(legacy) == 80.0
    assert _position_unrealized_pl(legacy) == 12.0


def test_parse_moomoo_news_row():
    item = _parse_moomoo_news_row(
        {
            "title": "NVDA rises on AI demand",
            "content": "Chipmaker gains.",
            "source": "Reuters",
            "publish_time": "2026-08-15 10:00:00",
            "related_securities": "US.NVDA,US.AMD",
        },
        default_symbol="NVDA",
    )
    assert item is not None
    assert item.headline.startswith("NVDA")
    assert item.symbols == ("NVDA", "AMD")


def test_entry_order_params_market_vs_limit():
    sdk = SimpleNamespace(
        OrderType=SimpleNamespace(MARKET="MARKET", NORMAL="NORMAL"),
    )
    market_req = OrderRequest(
        symbol="AAPL",
        qty=1,
        side=Side.BUY,
        asset_class=AssetClass.EQUITY,
        order_type=OrderType.MARKET,
    )
    otype, price, aux = MoomooBroker._entry_order_params(sdk, market_req)
    assert otype == "MARKET"
    assert price == 0.0
    assert aux is None

    limit_req = OrderRequest(
        symbol="AAPL",
        qty=1,
        side=Side.BUY,
        asset_class=AssetClass.EQUITY,
        order_type=OrderType.LIMIT,
        limit_price=150.0,
    )
    otype, price, aux = MoomooBroker._entry_order_params(sdk, limit_req)
    assert otype == "NORMAL"
    assert price == 150.0


def test_submit_order_places_protective_legs():
    broker = object.__new__(MoomooBroker)
    broker.is_live = False
    broker._unlocked = True
    broker._unlock_password = ""
    broker._market = "US"
    broker._acc_id = 0
    broker._acc_index = 0
    broker._trd_env = "SIMULATE"

    calls: list[dict] = []

    def place_order(**kwargs):
        calls.append(kwargs)
        idx = len(calls)
        row = MagicMock()
        row.get = lambda k, d="": f"oid-{idx}" if k == "order_id" else d
        data = MagicMock()
        data.__len__.return_value = 1
        data.iloc = [row]
        return 0, data

    broker._trade_ctx = SimpleNamespace(place_order=place_order)

    import aoa.brokerage.moomoo as mod

    fake_sdk = SimpleNamespace(
        RET_OK=0,
        TrdSide=SimpleNamespace(BUY="BUY", SELL="SELL"),
        OrderType=SimpleNamespace(MARKET="MARKET", NORMAL="NORMAL", STOP="STOP"),
        TimeInForce=SimpleNamespace(DAY="DAY", GTC="GTC"),
    )
    original = mod._require_sdk
    mod._require_sdk = lambda: fake_sdk
    try:
        req = OrderRequest(
            symbol="AAPL",
            qty=2,
            side=Side.BUY,
            asset_class=AssetClass.EQUITY,
            order_type=OrderType.MARKET,
            stop_loss_price=140.0,
            take_profit_price=180.0,
        )
        order = MoomooBroker.submit_order(broker, req)
    finally:
        mod._require_sdk = original

    assert order.id == "oid-1"
    assert len(calls) == 3
    assert calls[0]["order_type"] == "MARKET"
    assert calls[1]["order_type"] == "STOP"
    assert calls[1]["aux_price"] == 140.0
    assert calls[2]["price"] == 180.0
    assert len(order.raw["protective_legs"]) == 2
