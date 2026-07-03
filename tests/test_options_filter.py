"""Tests for options chain filtering."""

from __future__ import annotations

from aoa.agents.options import _filter_chain
from aoa.brokerage.models import OptionContract, OptionType


def _contract(*, oi: float = 500) -> OptionContract:
    return OptionContract(
        symbol="AAPL250117C00100000",
        underlying="AAPL",
        option_type=OptionType.CALL,
        strike=100.0,
        expiration="2025-01-17",
        bid=2.0,
        ask=2.2,
        open_interest=oi,
    )


def test_filter_keeps_liquid_contracts_with_open_interest():
    chain = [_contract(oi=500)]
    out = _filter_chain(chain, 100.0)
    assert len(out) == 1


def test_filter_keeps_contracts_when_open_interest_unknown():
    """Alpaca snapshots often omit OI; unknown (0) should not block the chain."""
    chain = [_contract(oi=0)]
    out = _filter_chain(chain, 100.0)
    assert len(out) == 1


def test_filter_rejects_low_open_interest():
    chain = [_contract(oi=5)]
    out = _filter_chain(chain, 100.0)
    assert len(out) == 0
