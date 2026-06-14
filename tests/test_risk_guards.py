"""Tests for the deterministic cash-account risk guardrails."""

from __future__ import annotations

from conftest import make_position

from aoa.agents.base import TradeProposal
from aoa.brokerage.models import Account, AssetClass, Side
from aoa.config import RiskLimits
from aoa.risk.guards import RiskGuards


def _account(equity=100_000.0, settled=100_000.0):
    return Account(
        equity=equity,
        cash=settled,
        buying_power=settled,
        settled_cash=settled,
        options_level=2,
    )


def _buy(symbol="AAPL", qty=10, price=100.0, asset_class=AssetClass.EQUITY, underlying=None):
    return TradeProposal(
        symbol=symbol,
        asset_class=asset_class,
        side=Side.BUY,
        qty=qty,
        rationale="test",
        est_price=price,
        underlying=underlying,
    )


def test_reasonable_buy_is_approved():
    guards = RiskGuards(RiskLimits())
    props = [_buy(qty=10, price=100)]  # $1,000 of a $100k book
    guards.evaluate_cycle(props, _account(), [], starting_equity=100_000)
    assert props[0].approved is True


def test_oversize_position_rejected():
    guards = RiskGuards(RiskLimits(max_position_pct=0.10))
    props = [_buy(qty=200, price=100)]  # $20,000 > 10% of $100k
    guards.evaluate_cycle(props, _account(), [], starting_equity=100_000)
    assert props[0].approved is False
    assert any("per-position cap" in n for n in props[0].risk_notes)


def test_equity_short_open_rejected():
    guards = RiskGuards(RiskLimits())
    short = TradeProposal(
        symbol="AAPL", asset_class=AssetClass.EQUITY, side=Side.SELL, qty=10,
        rationale="short", est_price=100.0,
    )
    guards.evaluate_cycle([short], _account(), [], starting_equity=100_000)
    assert short.approved is False
    assert any("short" in n for n in short.risk_notes)


def test_sell_to_close_existing_long_allowed():
    guards = RiskGuards(RiskLimits())
    pos = make_position("AAPL", qty=50, price=100.0)
    sell = TradeProposal(
        symbol="AAPL", asset_class=AssetClass.EQUITY, side=Side.SELL, qty=50,
        rationale="exit", est_price=100.0,
    )
    guards.evaluate_cycle([sell], _account(), [pos], starting_equity=100_000)
    assert sell.approved is True


def test_uncovered_short_option_rejected():
    guards = RiskGuards(RiskLimits())
    sell = TradeProposal(
        symbol="AAPL250117C00100000", asset_class=AssetClass.OPTION, side=Side.SELL,
        qty=1, rationale="naked call", est_price=2.0, underlying="AAPL",
    )
    guards.evaluate_cycle([sell], _account(), [], starting_equity=100_000)
    assert sell.approved is False
    assert any("uncovered" in n for n in sell.risk_notes)


def test_covered_call_allowed():
    guards = RiskGuards(RiskLimits())
    pos = make_position("AAPL", qty=100, price=100.0)  # 100 shares cover 1 contract
    sell = TradeProposal(
        symbol="AAPL250117C00100000", asset_class=AssetClass.OPTION, side=Side.SELL,
        qty=1, rationale="covered call", est_price=2.0, underlying="AAPL",
    )
    guards.evaluate_cycle([sell], _account(), [pos], starting_equity=100_000)
    assert sell.approved is True


def test_cash_buffer_enforced():
    guards = RiskGuards(RiskLimits(min_cash_buffer_pct=0.05, max_position_pct=1.0))
    # Settled cash 10k, buffer 5% of 100k equity = 5k. A 9k buy breaches it.
    acct = Account(equity=100_000, cash=10_000, buying_power=10_000, settled_cash=10_000)
    props = [_buy(qty=90, price=100)]  # $9,000
    guards.evaluate_cycle(props, acct, [], starting_equity=100_000)
    assert props[0].approved is False
    assert any("cash buffer" in n for n in props[0].risk_notes)


def test_daily_loss_kill_switch_blocks_new_risk():
    guards = RiskGuards(RiskLimits(max_daily_loss_pct=0.03))
    # Equity dropped from 100k to 96k => -4% < -3% limit.
    acct = _account(equity=96_000, settled=96_000)
    props = [_buy(qty=1, price=100)]
    guards.evaluate_cycle(props, acct, [], starting_equity=100_000)
    assert props[0].approved is False
    assert any("kill-switch" in n for n in props[0].risk_notes)


def test_per_cycle_order_cap():
    guards = RiskGuards(RiskLimits(max_orders_per_cycle=2, max_position_pct=1.0))
    props = [_buy(symbol=f"S{i}", qty=1, price=100) for i in range(4)]
    guards.evaluate_cycle(props, _account(), [], starting_equity=100_000)
    assert sum(p.approved for p in props) == 2


def test_position_cap_counts_existing_holding():
    # Already hold $9k of AAPL (9% of $100k). A further $2k buy => 11% > 10% cap.
    guards = RiskGuards(RiskLimits(max_position_pct=0.10))
    pos = make_position("AAPL", qty=90, price=100.0)  # market_value $9,000
    buy = _buy(symbol="AAPL", qty=20, price=100)  # $2,000
    guards.evaluate_cycle([buy], _account(), [pos], starting_equity=100_000)
    assert buy.approved is False
    assert any("per-position cap" in n for n in buy.risk_notes)


def test_position_cap_rolls_equity_and_options_under_one_name():
    # $9.9k of AAPL equity + a $200 AAPL option both count under name "AAPL".
    guards = RiskGuards(RiskLimits(max_position_pct=0.10))
    pos = make_position("AAPL", qty=99, price=100.0)  # $9,900
    opt = TradeProposal(
        symbol="AAPL250117C00100000", asset_class=AssetClass.OPTION, side=Side.BUY,
        qty=1, rationale="add", est_price=2.0, underlying="AAPL",  # $200 notional
    )
    guards.evaluate_cycle([opt], _account(), [pos], starting_equity=100_000)
    assert opt.approved is False
    assert any("AAPL" in n and "per-position cap" in n for n in opt.risk_notes)


def test_second_buy_same_name_in_cycle_blocked():
    # Two $6k buys of the same name in one cycle => second pushes past 10% cap.
    guards = RiskGuards(RiskLimits(max_position_pct=0.10))
    first = _buy(symbol="AAPL", qty=60, price=100)  # $6,000
    second = _buy(symbol="AAPL", qty=60, price=100)  # +$6,000 => $12k > $10k
    guards.evaluate_cycle([first, second], _account(), [], starting_equity=100_000)
    assert first.approved is True
    assert second.approved is False
