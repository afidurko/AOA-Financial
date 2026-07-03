"""Tests for options chain filtering."""

from __future__ import annotations

from aoa.agents.options import _filter_chain, _is_liquid_contract
from aoa.brokerage.models import OptionContract, OptionType


def test_is_liquid_contract_accepts_zero_oi_with_tight_spread():
    contract = OptionContract(
        symbol="AAPL250117C00100000",
        underlying="AAPL",
        option_type=OptionType.CALL,
        strike=100.0,
        expiration="2025-01-17",
        bid=2.0,
        ask=2.1,
        open_interest=0.0,
    )
    assert _is_liquid_contract(contract) is True


def test_is_liquid_contract_rejects_wide_spread_without_oi():
    contract = OptionContract(
        symbol="AAPL250117C00100000",
        underlying="AAPL",
        option_type=OptionType.CALL,
        strike=100.0,
        expiration="2025-01-17",
        bid=1.0,
        ask=2.0,
        open_interest=0.0,
    )
    assert _is_liquid_contract(contract) is False


def test_filter_chain_keeps_near_the_money_contracts():
    chain = [
        OptionContract(
            symbol="AAPL250117C00100000",
            underlying="AAPL",
            option_type=OptionType.CALL,
            strike=100.0,
            expiration="2025-01-17",
            bid=2.0,
            ask=2.1,
            open_interest=0.0,
        ),
        OptionContract(
            symbol="AAPL250117C00200000",
            underlying="AAPL",
            option_type=OptionType.CALL,
            strike=200.0,
            expiration="2025-01-17",
            bid=0.5,
            ask=0.6,
            open_interest=100.0,
        ),
    ]
    filtered = _filter_chain(chain, underlying_price=100.0)
    assert len(filtered) == 1
    assert filtered[0].strike == 100.0
