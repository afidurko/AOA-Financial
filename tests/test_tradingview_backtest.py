"""TradingView-semantics broker emulator: fills, exits, accounting, research helpers."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from aoa.brokerage.models import Bar
from aoa.tradingview import backtest as bt
from aoa.tradingview.backtest import (
    EmulatorConfig,
    Trade,
    max_drawdown_pct,
    monte_carlo_trades,
    objective_value,
    param_grid,
    run_backtest,
    sweep,
    walk_forward,
)
from aoa.tradingview.data import synthetic_bars
from aoa.tradingview.presets import CostModel, Preset, RiskModel, get_preset
from aoa.tradingview.rules import Signal

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bar(i: int, o: float, h: float, lo: float, c: float, *, step_s: int = 86400, start: datetime = T0) -> Bar:
    return Bar(start + timedelta(seconds=step_s * i), o, h, lo, c, 1000.0)


def _flat(closes: list[float], **kw) -> list[Bar]:
    return [_bar(i, c, c, c, c, **kw) for i, c in enumerate(closes)]


class Scripted:
    """Strategy stub: emits pre-scripted signals per bar index."""

    def __init__(self, preset: Preset, script: dict[int, Signal], *, atr: float = 1.0, warmup: int = 0) -> None:
        self.preset = preset
        self.warmup = warmup
        self.script = script
        self.atr = atr
        self.i = -1

    def on_bar(self, bar: Bar) -> Signal:
        self.i += 1
        sig = self.script.get(self.i, Signal())
        sig.ready = True
        sig.atr = self.atr
        return sig


def _preset(**risk) -> Preset:
    return Preset(
        name="test-preset",
        family="momentum_scalper",
        horizon="swing",
        market="equity",
        timeframe="1D",
        description="test",
        params={"ema_fast": 3, "ema_slow": 5, "rsi_len": 3},
        risk=RiskModel(**{"stop_atr": 0.0, "target_atr": 0.0, "qty_pct_equity": 10.0, **risk}),
        costs=CostModel(commission_pct=0.0, slippage_ticks=0, slippage_pct=0.0),
        allow_short=True,
    )


@pytest.fixture
def scripted(monkeypatch):
    def _install(script: dict[int, Signal], **kw):
        monkeypatch.setattr(bt, "build_strategy", lambda preset, fundamentals_ok=True: Scripted(preset, script, **kw))

    return _install


# --------------------------------------------------------------------------- #
# Fill semantics
# --------------------------------------------------------------------------- #


def test_entry_fills_next_bar_open_and_exit_on_signal(scripted) -> None:
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 102, 103, 101, 102),  # entry fills at open 102
        _bar(2, 104, 105, 103, 104),  # exit signal at close
        _bar(3, 106, 107, 105, 106),  # exit fills at open 106
        _bar(4, 106, 106, 106, 106),
    ]
    scripted({0: Signal(long_entry=True), 2: Signal(exit_long=True)})
    res = run_backtest(bars, _preset(), cfg=EmulatorConfig(initial_capital=100_000.0))
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.entry_index == 1 and t.entry_price == 102.0
    assert t.exit_index == 3 and t.exit_price == 106.0 and t.exit_reason == "signal"
    assert t.qty == math.floor(10_000 / 102)  # whole shares, 10% of equity
    assert t.pnl == pytest.approx((106 - 102) * t.qty)
    assert res.equity_curve[-1] == pytest.approx(100_000.0 + t.pnl)
    assert res.metrics["total_trades"] == 1 and res.metrics["win_rate_pct"] == 100.0


def test_fill_on_close_mirrors_process_orders_on_close(scripted) -> None:
    bars = _flat([100, 101, 102, 103])
    scripted({0: Signal(long_entry=True), 2: Signal(exit_long=True)})
    res = run_backtest(bars, _preset(), cfg=EmulatorConfig(fill_on_close=True))
    t = res.trades[0]
    assert (t.entry_index, t.entry_price) == (0, 100.0)
    assert (t.exit_index, t.exit_price) == (2, 102.0)


def test_stop_hit_intrabar_with_gap_fills_at_open(scripted) -> None:
    # entry at 100 (bar1 open), stop at 100 - 1.5*ATR(2) = 97; bar 2 gaps down to 95.
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 100, 101, 99, 100),
        _bar(2, 95, 96, 94, 95.5),
        _bar(3, 95, 95, 95, 95),
    ]
    scripted({0: Signal(long_entry=True)}, atr=2.0)
    res = run_backtest(bars, _preset(stop_atr=1.5))
    t = res.trades[0]
    assert t.stop == pytest.approx(97.0)
    assert t.exit_reason == "stop" and t.exit_index == 2
    assert t.exit_price == 95.0  # gapped through → open, not the level


def test_target_hit_intrabar_fills_at_level(scripted) -> None:
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 100, 101, 99, 100),
        _bar(2, 100, 106, 99.5, 104),  # target 100 + 2.5*2 = 105 touched
    ]
    scripted({0: Signal(long_entry=True)}, atr=2.0)
    res = run_backtest(bars, _preset(target_atr=2.5))
    t = res.trades[0]
    assert t.exit_reason == "target" and t.exit_price == pytest.approx(105.0)


def test_both_levels_touched_uses_nearer_extreme_or_conservative(scripted) -> None:
    # long from 100, stop 97, target 105; bar opens 100, high 106 (dist 6), low 96 (dist 4) → low first → stop.
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 100, 100, 100), _bar(2, 100, 106, 96, 101)]
    scripted({0: Signal(long_entry=True)}, atr=2.0)
    res = run_backtest(bars, _preset(stop_atr=1.5, target_atr=2.5))
    assert res.trades[0].exit_reason == "stop"
    # high reached first (dist to high 1 < dist to low 4) → target …
    bars2 = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 100, 100, 100), _bar(2, 105, 106, 96, 101)]
    scripted({0: Signal(long_entry=True)}, atr=2.0)
    res2 = run_backtest(bars2, _preset(stop_atr=1.5, target_atr=2.5))
    assert res2.trades[0].exit_reason == "target"
    # … unless conservative mode forces the worst case.
    scripted({0: Signal(long_entry=True)}, atr=2.0)
    res3 = run_backtest(bars2, _preset(stop_atr=1.5, target_atr=2.5), cfg=EmulatorConfig(conservative_intrabar=True))
    assert res3.trades[0].exit_reason == "stop"


def test_trailing_stop_ratchets_only_upward_for_longs(scripted) -> None:
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 100, 100, 100, 100),  # entry @100; trail after close = 100-2 = 98
        _bar(2, 104, 104, 103, 104),  # trail → 102
        _bar(3, 103, 103, 102.5, 103),  # trail stays 102 (would be 101)
        _bar(4, 102.5, 102.5, 101.0, 101.5),  # low 101 <= 102 → stop
    ]
    scripted({0: Signal(long_entry=True)}, atr=1.0)
    res = run_backtest(bars, _preset(trail_atr=2.0))
    t = res.trades[0]
    assert t.exit_reason == "stop" and t.exit_index == 4
    assert t.exit_price == pytest.approx(102.0)


def test_time_stop_exits_after_max_bars(scripted) -> None:
    bars = _flat([100] * 8)
    scripted({0: Signal(long_entry=True)})
    res = run_backtest(bars, _preset(max_bars_in_trade=3))
    t = res.trades[0]
    assert t.exit_reason == "time" and t.entry_index == 1 and t.exit_index == 5


def test_session_flat_into_close_and_no_entries_outside(scripted) -> None:
    # 5-minute equity bars starting 15:40 ET (20:40 UTC in January); session ends 15:55.
    start = datetime(2024, 1, 8, 20, 40, tzinfo=timezone.utc)
    bars = [_bar(i, 100, 100, 100, 100, step_s=300, start=start) for i in range(6)]
    script = {0: Signal(long_entry=True), 2: Signal(long_entry=True), 4: Signal(long_entry=True)}
    scripted(script)
    p = Preset(**{**_preset().__dict__, "timeframe": "5", "risk": RiskModel(stop_atr=0, target_atr=0, session="0935-1555")})
    res = run_backtest(bars, p)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.entry_index == 1  # 15:45
    assert t.exit_reason == "session_end"
    assert t.exit_index == 2  # 15:50 is the last in-session bar (next bar 15:55 is outside)
    assert res.metrics["exit_reasons"] == {"session_end": 1}


def test_max_trades_per_day_cap(scripted) -> None:
    start = datetime(2024, 1, 8, 15, 0, tzinfo=timezone.utc)  # 10:00 ET
    bars = [_bar(i, 100, 100, 100, 100, step_s=300, start=start) for i in range(12)]
    script = {i: Signal(long_entry=True) for i in range(0, 12, 2)}
    script.update({i: Signal(exit_long=True) for i in range(1, 12, 2)})
    scripted(script)
    p = Preset(**{**_preset().__dict__, "timeframe": "5", "risk": RiskModel(stop_atr=0, target_atr=0, max_trades_per_day=2)})
    res = run_backtest(bars, p)
    assert len(res.trades) == 2


def test_short_trade_accounting_symmetric(scripted) -> None:
    bars = _flat([100, 100, 90, 90, 90])
    scripted({0: Signal(short_entry=True), 2: Signal(exit_short=True)})
    res = run_backtest(bars, _preset(), cfg=EmulatorConfig(initial_capital=100_000.0))
    t = res.trades[0]
    assert t.side == "short" and t.entry_price == 100.0 and t.exit_price == 90.0
    assert t.pnl == pytest.approx(10.0 * t.qty)
    assert res.equity_curve[-1] == pytest.approx(100_000.0 + t.pnl)
    # mark-to-market while short and price falls → equity rises
    assert res.equity_curve[2] > res.equity_curve[1]


def test_commission_and_slippage_reduce_pnl(scripted) -> None:
    bars = _flat([100, 100, 100, 100])
    scripted({0: Signal(long_entry=True), 2: Signal(exit_long=True)})
    p = Preset(**{**_preset().__dict__, "costs": CostModel(commission_pct=0.1, slippage_ticks=1, slippage_pct=0.05)})
    res = run_backtest(bars, p)
    t = res.trades[0]
    assert t.entry_price == pytest.approx(100.05)  # buy slips up
    assert t.exit_price == pytest.approx(99.95)  # sell slips down
    assert t.commission > 0 and t.pnl < 0
    assert res.metrics["commission_paid"] == pytest.approx(round(t.commission, 2))
    scripted({0: Signal(long_entry=True), 2: Signal(exit_long=True)})
    tick = run_backtest(bars, p, cfg=EmulatorConfig(tick_size=0.01))
    assert tick.trades[0].entry_price == pytest.approx(100.01)


def test_open_trade_force_closed_at_end(scripted) -> None:
    bars = _flat([100, 100, 110])
    scripted({0: Signal(long_entry=True)})
    res = run_backtest(bars, _preset())
    t = res.trades[0]
    assert t.exit_reason == "end" and t.exit_price == 110.0
    assert not t.is_open


def test_start_index_delays_first_entry(scripted) -> None:
    bars = _flat([100] * 6)
    scripted({i: Signal(long_entry=True) for i in range(6)})
    res = run_backtest(bars, _preset(), start_index=3)
    assert res.trades[0].entry_index == 4


def test_crypto_uses_fractional_qty() -> None:
    preset = get_preset("swing-crypto-4h-momentum")
    bars = synthetic_bars("BTC-USD", preset.tf, n=1500, seed=3, market="crypto", start_price=60_000.0)
    res = run_backtest(bars, preset, symbol="BTC-USD")
    assert res.trades, "expected trades on a 1500-bar synthetic series"
    assert any(t.qty != math.floor(t.qty) for t in res.trades)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def test_max_drawdown() -> None:
    assert max_drawdown_pct([100, 120, 90, 130]) == pytest.approx(-25.0)
    assert max_drawdown_pct([100, 101, 102]) == 0.0
    assert max_drawdown_pct([]) == 0.0


def test_metrics_are_consistent(scripted) -> None:
    bars = _flat([100, 100, 110, 110, 100, 100, 95, 95, 100])
    script = {0: Signal(long_entry=True), 2: Signal(exit_long=True), 4: Signal(long_entry=True), 6: Signal(exit_long=True)}
    scripted(script)
    res = run_backtest(bars, _preset())
    m = res.metrics
    assert m["total_trades"] == 2
    assert m["win_rate_pct"] == 50.0
    assert m["gross_profit"] > 0 and m["gross_loss"] > 0
    assert m["profit_factor"] == pytest.approx(m["gross_profit"] / m["gross_loss"], rel=1e-3)
    assert m["net_profit"] == pytest.approx(m["gross_profit"] - m["gross_loss"], abs=0.02)
    assert m["exit_reasons"] == {"signal": 2}
    assert m["largest_loss_pct"] < 0 < m["largest_win_pct"]
    assert 0 < m["exposure_pct"] <= 100
    d = res.to_dict(include_trades=True)
    assert len(d["trades"]) == 2 and d["metrics"] == m


def test_backtest_is_deterministic() -> None:
    preset = get_preset("scalp-equity-5m-orderflow")
    bars = synthetic_bars("AAPL", preset.tf, n=1200, seed=5)
    a = run_backtest(bars, preset, symbol="AAPL")
    b = run_backtest(bars, preset, symbol="AAPL")
    assert a.metrics == b.metrics
    assert [t.to_dict() for t in a.trades] == [t.to_dict() for t in b.trades]


def test_objective_value_guards() -> None:
    assert objective_value({"total_trades": 2, "sqn": 5.0}, "sqn") == -math.inf
    assert objective_value({"total_trades": 10, "profit_factor": float("inf")}, "profit_factor") == 1e9
    assert objective_value({"total_trades": 10, "sqn": 1.5}, "sqn") == 1.5


# --------------------------------------------------------------------------- #
# Research helpers
# --------------------------------------------------------------------------- #


def test_param_grid_and_sweep_ranking() -> None:
    preset = get_preset("swing-equity-1d-trend")
    grid = {"st_mult": (2.0, 3.0), "atr_len": (10, 14)}
    combos = param_grid(preset, grid)
    assert len(combos) == 4 and {"st_mult": 2.0, "atr_len": 10} in combos
    bars = synthetic_bars("MSFT", preset.tf, n=800, seed=9)
    rows = sweep(bars, preset, grid=grid, objective="net_profit_pct", min_trades=1)
    assert len(rows) == 4
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    assert all("metrics" in r and "params" in r for r in rows)


def test_walk_forward_folds_are_out_of_sample() -> None:
    preset = get_preset("swing-equity-1d-trend")
    bars = synthetic_bars("MSFT", preset.tf, n=1000, seed=4)
    wf = walk_forward(bars, preset, folds=3, min_trades=1, grid={"st_mult": (2.0, 3.0)})
    assert len(wf.folds) == 3
    for f in wf.folds:
        is_s, is_e = f["is_range"]
        oos_s, oos_e = f["oos_range"]
        assert is_e == oos_s and oos_e > oos_s and is_e > is_s
        assert f["best_params"]["st_mult"] in (2.0, 3.0)
    assert wf.folds[-1]["oos_range"][1] == len(bars)
    assert wf.oos_equity and wf.oos_equity[0] == pytest.approx(100_000.0)
    assert set(wf.oos_metrics) >= {"net_profit_pct", "max_drawdown_pct", "total_trades", "folds_profitable"}
    d = wf.to_dict()
    assert d["preset"] == preset.name and len(d["folds"]) == 3


def test_walk_forward_respects_fundamentals_gate() -> None:
    preset = get_preset("position-equity-1d-fundamental")
    bars = _flat([100.0 * (1.001**i) for i in range(900)])
    open_gate = walk_forward(bars, preset, folds=2, min_trades=1, grid={"min_mom_pct": (0.0,)}, fundamentals_ok=True)
    closed = walk_forward(bars, preset, folds=2, min_trades=1, grid={"min_mom_pct": (0.0,)}, fundamentals_ok=False)
    assert open_gate.oos_metrics["total_trades"] > 0
    assert closed.oos_metrics["total_trades"] == 0 and closed.oos_metrics["net_profit_pct"] == 0.0
    assert all(f["is_score"] is None for f in closed.folds)  # nothing to fit on either


def test_walk_forward_anchored_grows_in_sample() -> None:
    preset = get_preset("swing-equity-1d-trend")
    bars = synthetic_bars("MSFT", preset.tf, n=800, seed=4)
    wf = walk_forward(bars, preset, folds=3, anchored=True, min_trades=1, grid={"st_mult": (3.0,)})
    assert all(f["is_range"][0] == 0 for f in wf.folds)
    with pytest.raises(ValueError):
        walk_forward(bars[:50], preset, folds=4)


def test_monte_carlo_drawdown_distribution() -> None:
    def mk(pnl_pct: float) -> Trade:
        t = Trade(side="long", entry_index=0, entry_time=T0, entry_price=100.0, qty=1.0)
        t.exit_index, t.exit_price, t.exit_time = 1, 100.0 * (1 + pnl_pct / 100.0), T0
        return t

    trades = [mk(x) for x in (5, -3, 4, -6, 2, 3, -2, 7, -4, 1)]
    mc = monte_carlo_trades(trades, n_paths=300, seed=1, ruin_dd_pct=8.0)
    assert mc["ok"] and mc["n_trades"] == 10
    dd = mc["max_drawdown_pct"]
    assert dd["p5"] <= dd["p50"] <= dd["p95"] <= 0
    assert 0.0 <= mc["p_drawdown_exceeds"]["8pct"] <= 1.0
    expected = (math.prod(1 + x / 100.0 for x in (5, -3, 4, -6, 2, 3, -2, 7, -4, 1)) - 1) * 100
    assert mc["final_return_pct"] == pytest.approx(expected, abs=1e-3)
    assert monte_carlo_trades(trades[:1])["ok"] is False
