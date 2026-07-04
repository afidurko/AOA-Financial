"""Tests for FinancePy-backed Andrea quant context."""

from __future__ import annotations

import pytest

from aoa.brokerage.models import OptionContract, OptionType
from aoa.risk.options_quant import HAS_FINANCEPY, build_andrea_quant_context

pytestmark = pytest.mark.skipif(not HAS_FINANCEPY, reason="financepy extra not installed")


def _expiry() -> str:
    return "2026-12-18"


def _put(strike: float, *, mid: float = 2.5, iv: float = 0.30) -> OptionContract:
    exp = _expiry()
    return OptionContract(
        symbol=f"AAPL{exp.replace('-', '')}P{int(strike * 1000):08d}",
        underlying="AAPL",
        option_type=OptionType.PUT,
        strike=strike,
        expiration=exp,
        bid=mid - 0.05,
        ask=mid + 0.05,
        implied_volatility=iv,
        delta=-0.25,
    )


def _call(strike: float, *, mid: float = 3.0, iv: float = 0.28) -> OptionContract:
    exp = _expiry()
    return OptionContract(
        symbol=f"AAPL{exp.replace('-', '')}C{int(strike * 1000):08d}",
        underlying="AAPL",
        option_type=OptionType.CALL,
        strike=strike,
        expiration=exp,
        bid=mid - 0.05,
        ask=mid + 0.05,
        implied_volatility=iv,
        delta=0.45,
    )


def test_build_context_without_spot_returns_none():
    assert build_andrea_quant_context("AAPL", None, option_chain=[]) is None


def test_protective_put_hedge_in_context():
    spot = 100.0
    chain = [_put(95.0), _put(90.0)]
    ctx = build_andrea_quant_context("AAPL", spot, option_chain=chain)
    assert ctx is not None
    assert ctx["source"] == "financepy"
    hedge = ctx["protective_put_hedge"]
    assert hedge["type"] == "put"
    assert hedge["premium_per_contract_usd"] > 0
    assert hedge["greeks"]["delta"] is not None


def test_proposed_option_analyzed_when_present():
    spot = 100.0
    call = _call(105.0)
    chain = [call, _put(95.0)]
    idea = {"contract_symbol": call.symbol, "strategy": "long_call"}
    ctx = build_andrea_quant_context(
        "AAPL",
        spot,
        options_idea=idea,
        option_chain=chain,
    )
    assert ctx is not None
    proposed = ctx["proposed_option"]
    assert proposed["symbol"] == call.symbol
    assert proposed["model_fair_value"] is not None
    assert proposed["market_mid"] == call.mid
    assert "mispricing_pct" in proposed


def test_build_symbol_context_includes_financepy():
    from aoa.team.andrea import _build_symbol_context

    ctx = _build_symbol_context(
        "AAPL",
        prop=None,
        trend=None,
        algo=None,
        market=None,
        catalyst=None,
        options_idea=None,
        quant_context={"source": "financepy", "spot": 100.0},
        account={"equity": 100_000.0},
        max_position_pct=0.10,
    )
    assert "FinancePy quant context" in ctx
