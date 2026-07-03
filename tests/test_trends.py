"""Tests for historical trend analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aoa.brokerage.models import Bar
from aoa.simulation import trends


def _bars(closes):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=base + timedelta(days=i),
            open=c,
            high=c * 1.02,
            low=c * 0.98,
            close=c,
            volume=1_000,
        )
        for i, c in enumerate(closes)
    ]


def test_simple_and_log_returns_lengths():
    closes = [100, 110, 99]
    assert len(trends.simple_returns(closes)) == 2
    assert len(trends.log_returns(closes)) == 2
    assert round(trends.simple_returns([100, 110])[0], 4) == 0.10


def test_linear_regression_perfect_line():
    slope, intercept, r2 = trends.linear_regression([1, 2, 3, 4, 5])
    assert round(slope, 6) == 1.0
    assert round(intercept, 6) == 1.0
    assert r2 == 1.0


def test_max_drawdown_basic():
    # Peak 100 → trough 50 == -50%.
    assert trends.max_drawdown([100, 120, 60, 50, 80]) == round((50 / 120 - 1) * 100, 2)
    assert trends.max_drawdown([1]) == 0.0


def test_current_drawdown():
    assert trends.current_drawdown([100, 200, 150]) == -25.0


def test_drawdown_events_detects_and_orders():
    closes = [100, 120, 84, 130, 200, 100, 210]  # two big drawdowns
    events = trends.drawdown_events(closes, threshold_pct=10.0)
    assert len(events) == 2
    # Deepest first; the 200→100 (-50%) event leads.
    assert events[0].depth_pct <= events[1].depth_pct
    assert events[0].depth_pct == -50.0
    assert events[0].recovered is True


def test_drawdown_event_ongoing_when_unrecovered():
    closes = [100, 120, 60]  # never recovers to peak
    events = trends.drawdown_events(closes, threshold_pct=10.0)
    assert len(events) == 1
    assert events[0].recovered is False
    assert events[0].recovery_index is None


def test_return_stats_constant_series_is_flat():
    stats = trends.return_stats([100.0] * 30)
    assert stats.std_daily_pct == 0.0
    assert stats.mean_daily_pct == 0.0


def test_analyze_trends_uptrend():
    closes = [100 * (1.01**i) for i in range(60)]  # steady compounding uptrend
    a = trends.analyze_trends(_bars(closes), "TEST")
    assert a is not None
    assert a.trend == "up"
    assert a.total_return_pct > 0
    assert a.regime.startswith("bull")
    assert a.n_bars == 60


def test_analyze_trends_downtrend_regime():
    closes = [100 * (0.99**i) for i in range(60)]
    a = trends.analyze_trends(_bars(closes), "TEST")
    assert a is not None
    assert a.trend == "down"
    assert "bear" in a.regime


def test_analyze_trends_insufficient_data():
    assert trends.analyze_trends(_bars([100]), "X") is None


def test_to_dict_is_serializable():
    closes = [100 * (1.005**i) for i in range(40)]
    a = trends.analyze_trends(_bars(closes), "TEST")
    d = a.to_dict()
    assert d["symbol"] == "TEST"
    assert "returns" in d and "drawdowns" in d
