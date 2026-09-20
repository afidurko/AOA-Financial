"""Indicator kernels and strategy rules for the TradingView desk (offline)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aoa.brokerage.models import Bar
from aoa.data import indicators as legacy
from aoa.tradingview.data import synthetic_bars
from aoa.tradingview.presets import PRESETS, get_preset, get_timeframe
from aoa.tradingview.rules import (
    Atr,
    Ema,
    Rsi,
    SessionVwap,
    Sma,
    Stdev,
    Supertrend,
    build_strategy,
    crossover,
    crossunder,
    in_session,
)


def _bars(closes: list[float], *, start: datetime | None = None, step_s: int = 86400) -> list[Bar]:
    ts = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = []
    for c in closes:
        out.append(Bar(ts, c, c * 1.01, c * 0.99, c, 1000.0))
        ts += timedelta(seconds=step_s)
    return out


def test_sma_matches_legacy_indicator() -> None:
    closes = [float(x) for x in range(1, 60)]
    k = Sma(20)
    last = None
    for c in closes:
        last = k.update(c)
    assert last == pytest.approx(legacy.sma(closes, 20))


def test_rsi_matches_wilder_reference() -> None:
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
    k = Rsi(14)
    last = None
    for c in closes:
        last = k.update(c)
    assert last == pytest.approx(legacy.rsi(closes, 14), abs=0.05)


def test_atr_matches_legacy_indicator() -> None:
    bars = synthetic_bars("T", get_timeframe("1D"), n=120, seed=1)
    k = Atr(14)
    last = None
    for b in bars:
        last = k.update(b)
    # legacy.atr rounds to 4 decimals
    assert last == pytest.approx(legacy.atr(bars, 14), abs=1e-4)


def test_ema_and_stdev_basic() -> None:
    e = Ema(3)
    assert e.update(1.0) is None
    assert e.update(1.0) is None
    assert e.update(1.0) == pytest.approx(1.0)
    s = Stdev(4)
    for x in (2.0, 4.0, 4.0, 4.0):
        v = s.update(x)
    assert v == pytest.approx(0.8660254)
    assert s.mean == pytest.approx(3.5)


def test_supertrend_direction_flips_on_reversal() -> None:
    ups = [100 + i for i in range(60)]
    downs = [160 - 2 * i for i in range(60)]
    st = Supertrend(3.0, 10)
    dirs = [st.update(b) for b in _bars(ups + downs)]
    assert -1 in dirs[20:60]  # uptrend detected
    assert dirs[-1] == 1  # downtrend at the end


def test_session_vwap_resets_each_day() -> None:
    start = datetime(2024, 3, 4, 14, 30, tzinfo=timezone.utc)  # 09:30 New York (EST)
    bars = _bars([10, 20, 30], start=start, step_s=3600)
    v = SessionVwap("equity")
    for b in bars:
        v.update(b)
    day1 = v.value
    v.update(Bar(start + timedelta(days=1), 5, 5, 5, 5, 1.0))
    assert day1 != pytest.approx(5.0)
    assert v.value == pytest.approx(5.0)


def test_crossover_helpers() -> None:
    assert crossover(1.0, 3.0, 2.0, 2.0)
    assert not crossover(3.0, 4.0, 2.0, 2.0)
    assert crossunder(3.0, 1.0, 2.0, 2.0)
    assert not crossunder(None, 1.0, 2.0, 2.0)


def test_in_session_equity_uses_new_york_time() -> None:
    ts = datetime(2024, 3, 4, 14, 45, tzinfo=timezone.utc)  # 09:45 ET
    assert in_session(ts, "0935-1555", "equity")
    late = datetime(2024, 3, 4, 21, 0, tzinfo=timezone.utc)  # 16:00 ET
    assert not in_session(late, "0935-1555", "equity")
    assert in_session(late, None, "equity")


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_every_preset_builds_and_emits_ready_signals(name: str) -> None:
    preset = get_preset(name)
    strat = build_strategy(preset)
    bars = synthetic_bars("T", preset.tf, n=max(strat.warmup * 3, 400), seed=11, market=preset.market)
    ready = 0
    fired = 0
    for b in bars:
        sig = strat.on_bar(b)
        ready += sig.ready
        fired += sig.any()
        if not preset.allow_short:
            assert not sig.short_entry and not sig.exit_short
    assert ready > 0
    assert strat.warmup > 0


def test_fundamental_gate_blocks_long_entries() -> None:
    preset = get_preset("position-equity-1d-fundamental")
    # Steady 0.1%/day uptrend: price > SMA200 and 12-1 momentum well above 5%.
    bars = _bars([100.0 * (1.001**i) for i in range(600)])
    blocked = build_strategy(preset, fundamentals_ok=False)
    allowed = build_strategy(preset, fundamentals_ok=True)
    assert not any(blocked.on_bar(b).long_entry for b in bars)
    assert any(allowed.on_bar(b).long_entry for b in bars)
