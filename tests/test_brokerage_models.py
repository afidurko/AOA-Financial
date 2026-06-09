"""Tests for broker-neutral models and OCC option-symbol parsing."""

from __future__ import annotations

from aoa.brokerage.alpaca import _parse_occ
from aoa.brokerage.models import AssetClass, OptionType, OrderRequest, Quote, Side


def test_quote_mid_and_spread():
    q = Quote(symbol="AAPL", bid=100.0, ask=100.5)
    assert q.mid == 100.25
    assert q.spread == 0.5


def test_quote_mid_falls_back_to_ask_when_no_bid():
    q = Quote(symbol="AAPL", bid=0.0, ask=100.5)
    assert q.mid == 100.5


def test_parse_occ_call():
    otype, strike, expiry = _parse_occ("AAPL250117C00150000")
    assert otype is OptionType.CALL
    assert strike == 150.0
    assert expiry == "2025-01-17"


def test_parse_occ_put_with_fractional_strike():
    otype, strike, expiry = _parse_occ("SPY250620P00432500")
    assert otype is OptionType.PUT
    assert strike == 432.5
    assert expiry == "2025-06-20"


def test_parse_occ_rejects_garbage():
    assert _parse_occ("NOTANOPTION") is None
    assert _parse_occ("") is None


def test_order_request_notional_option_multiplier():
    req = OrderRequest(
        symbol="AAPL250117C00150000",
        qty=2,
        side=Side.BUY,
        asset_class=AssetClass.OPTION,
    )
    # 2 contracts * $3.00 * 100 multiplier = $600
    assert req.notional_estimate(3.0) == 600.0
