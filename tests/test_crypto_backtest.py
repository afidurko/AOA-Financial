"""Bracketed backtester tests: the 32%/26% bracket is structural (offline)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from aoa.crypto.assets import get_asset
from aoa.crypto.backtest import (
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    BracketPolicy,
    CryptoBacktester,
)
from aoa.crypto.history import DailyCandle
from aoa.crypto.training import DayByDayTrainer


def _tape(day0: date, closes: list[float], *, span: float = 0.015) -> list[DailyCandle]:
    return [
        DailyCandle(
            day=day0 + timedelta(days=i),
            open=c * (1 - span / 3),
            high=c * (1 + span),
            low=c * (1 - span),
            close=c,
            volume=10.0,
            source="test",
        )
        for i, c in enumerate(closes)
    ]


def _bull_tape(n: int = 500) -> list[DailyCandle]:
    closes = []
    price = 100.0
    for i in range(n):
        price *= 1.0 + 0.005 + 0.004 * math.sin(i / 5.0)
        closes.append(price)
    return _tape(date(2016, 1, 1), closes)


class _AlwaysBuy:
    """Minimal strategy stub: always long, never learns."""

    def decide(self, feats):
        return "buy", 1.0

    def learn(self, feats, next_ret, candle=None):
        pass


def _crash_tape(n_up: int = 200, n_down: int = 120) -> list[DailyCandle]:
    closes = []
    price = 100.0
    for i in range(n_up):
        price *= 1.0 + 0.006 + 0.003 * math.sin(i / 4.0)
        closes.append(price)
    for _ in range(n_down):
        price *= 0.985
        closes.append(price)
    return _tape(date(2016, 1, 1), closes)


class TestBracketPolicy:
    def test_defaults_are_the_mandated_32_26(self):
        policy = BracketPolicy()
        assert policy.take_profit_pct == TAKE_PROFIT_PCT == 0.32
        assert policy.stop_loss_pct == STOP_LOSS_PCT == 0.26

    def test_attach_computes_prices_before_execution(self):
        bracket = BracketPolicy().attach(100.0)
        assert bracket.take_profit == pytest.approx(132.0)
        assert bracket.stop_loss == pytest.approx(74.0)

    def test_invalid_policy_or_price_rejected(self):
        with pytest.raises(ValueError):
            BracketPolicy(take_profit_pct=0.0)
        with pytest.raises(ValueError):
            BracketPolicy(stop_loss_pct=1.5)
        with pytest.raises(ValueError):
            BracketPolicy().attach(0.0)


class TestBacktester:
    def _run(self, tape, **kwargs):
        asset = get_asset("BTC")
        trainer = DayByDayTrainer(asset, model_dir=kwargs.pop("model_dir"))
        bt = CryptoBacktester(asset, **kwargs)
        return bt.run(tape, trainer, start=tape[0].day)

    def test_every_trade_respects_the_bracket(self, tmp_path):
        result = self._run(_crash_tape(), model_dir=tmp_path)
        for trade in result.trades:
            # Gap-through fills can be beyond the trigger, never inside it.
            if trade.exit_reason == "take-profit":
                assert trade.return_pct >= 31.5
            elif trade.exit_reason == "stop-loss":
                assert trade.return_pct <= -25.5

    def test_bull_tape_generates_take_profit_exits(self, tmp_path):
        result = self._run(_bull_tape(), model_dir=tmp_path)
        assert result.trades, "expected the learner to trade a persistent bull tape"
        assert result.take_profit_exits >= 1
        assert result.total_return_pct > 0

    def test_equity_curve_and_accounting_are_consistent(self, tmp_path):
        result = self._run(_bull_tape(), model_dir=tmp_path)
        assert len(result.equity_curve) == result.market_days
        assert result.ending_equity == pytest.approx(
            result.starting_cash * (1 + result.total_return_pct / 100), rel=1e-9
        )
        assert result.fees_paid > 0  # fees actually charged

    def test_too_little_data_raises(self, tmp_path):
        tape = _tape(date(2020, 1, 1), [1.0] * 10)
        with pytest.raises(ValueError):
            self._run(tape, model_dir=tmp_path)

    def test_custom_policy_flows_through(self, tmp_path):
        result = self._run(
            _bull_tape(),
            model_dir=tmp_path,
            policy=BracketPolicy(take_profit_pct=0.10, stop_loss_pct=0.08),
        )
        assert result.policy.take_profit_pct == 0.10
        for trade in result.trades:
            if trade.exit_reason == "take-profit":
                assert trade.return_pct >= 9.7

    def test_gap_down_through_stop_fills_at_the_worse_open(self):
        """A −40% overnight gap must fill at the open, not the stop price."""
        asset = get_asset("BTC")
        tape = _tape(date(2020, 1, 1), [100.0] * 40, span=0.001)
        gap_open = 55.0  # far below the −26% stop (≈74) of a ~100 entry
        tape.append(
            DailyCandle(
                day=date(2020, 2, 10),
                open=gap_open,
                high=gap_open * 1.02,
                low=gap_open * 0.98,
                close=gap_open,
                volume=1.0,
            )
        )
        tape.extend(_tape(date(2020, 2, 11), [55.0] * 10, span=0.001))
        bt = CryptoBacktester(asset, warmup_days=2)
        result = bt.run(tape, _AlwaysBuy(), start=tape[0].day)
        stops = [t for t in result.trades if t.exit_reason == "stop-loss"]
        assert stops, "expected the gap to trigger the stop"
        assert stops[0].exit_price == pytest.approx(gap_open)
        assert stops[0].return_pct < -40.0  # honestly worse than −26%

    def test_gap_up_through_target_fills_at_the_better_open(self):
        asset = get_asset("BTC")
        tape = _tape(date(2020, 1, 1), [100.0] * 40, span=0.001)
        gap_open = 150.0  # far above the +32% target (≈132)
        tape.append(
            DailyCandle(
                day=date(2020, 2, 10),
                open=gap_open,
                high=gap_open * 1.02,
                low=gap_open * 0.98,
                close=gap_open,
                volume=1.0,
            )
        )
        tape.extend(_tape(date(2020, 2, 11), [150.0] * 10, span=0.001))
        bt = CryptoBacktester(asset, warmup_days=2)
        result = bt.run(tape, _AlwaysBuy(), start=tape[0].day)
        targets = [t for t in result.trades if t.exit_reason == "take-profit"]
        assert targets, "expected the gap to hit the target"
        assert targets[0].exit_price == pytest.approx(gap_open)
        assert targets[0].return_pct > 45.0  # honestly better than +32%

    def test_entry_execution_requires_valid_bracket(self):
        asset = get_asset("BTC")
        bt = CryptoBacktester(asset)
        candle = DailyCandle(
            day=date(2020, 1, 2), open=100.0, high=101.0, low=99.0, close=100.5, volume=1.0
        )
        position, cash_left, fee = bt._execute_entry(candle, 1000.0)
        assert position.bracket.take_profit > candle.open > position.bracket.stop_loss
        assert cash_left == 0.0 and fee > 0
