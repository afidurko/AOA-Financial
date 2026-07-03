"""Tests for agent resilience when the LLM is unavailable."""

from __future__ import annotations

from aoa.agents.base import Direction
from aoa.agents.scanner import ScannerAgent
from aoa.agents.technical import TechnicalAgent
from aoa.brokerage.models import Quote
from aoa.data.market_data import SymbolSnapshot
from aoa.llm.client import LLMError


class FailingLLM:
    model = "fake"

    def structured(self, *args, **kwargs):
        raise LLMError("down")


def _snap():
    return SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99.0, ask=101.0),
        technicals={"last_close": 100.0},
    )


def test_scanner_returns_empty_on_llm_failure():
    agent = ScannerAgent(FailingLLM())
    assert agent.scan({"AAPL": _snap()}) == []


def test_technical_returns_neutral_on_llm_failure():
    agent = TechnicalAgent(FailingLLM())
    signal = agent.analyze(_snap())
    assert signal.direction is Direction.NEUTRAL
    assert signal.conviction == 0.0
