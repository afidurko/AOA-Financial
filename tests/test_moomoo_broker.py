"""Tests for Moomoo symbol helpers."""

from __future__ import annotations

import pytest

from aoa.brokerage.base import BrokerError
from aoa.brokerage.moomoo import (
    _first_book_level,
    _parse_moomoo_option,
    _parse_option_tail,
    from_moomoo_code,
    probe_opend,
    to_moomoo_code,
)


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
