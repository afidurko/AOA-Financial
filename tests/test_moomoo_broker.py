"""Tests for Moomoo symbol helpers."""

from __future__ import annotations

import pytest

from aoa.brokerage.base import BrokerError
from aoa.brokerage.moomoo import (
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
