"""Tests for Moomoo symbol helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from aoa.brokerage.base import BrokerError
from aoa.brokerage.moomoo import (
    MoomooBroker,
    _parse_moomoo_option,
    _parse_option_tail,
    from_moomoo_code,
    opend_reachable,
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


def test_opend_reachable_false_on_refused():
    with patch("aoa.brokerage.moomoo.socket.create_connection", side_effect=ConnectionRefusedError):
        assert opend_reachable("127.0.0.1", 11111) is False


def test_moomoo_broker_raises_when_opend_unreachable():
    with patch("aoa.brokerage.moomoo.opend_reachable", return_value=False):
        with pytest.raises(BrokerError, match="not reachable"):
            MoomooBroker()
