"""Tests for the pure-Python technical indicators."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aoa.brokerage.models import Bar
from aoa.data import indicators


def _bars(closes):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=base + timedelta(days=i),
            open=c,
            high=c * 1.01,
            low=c * 0.99,
            close=c,
            volume=1000,
        )
        for i, c in enumerate(closes)
    ]


def test_sma_basic():
    assert indicators.sma([1, 2, 3, 4, 5], 5) == 3.0
    assert indicators.sma([1, 2, 3], 5) is None


def test_ema_matches_known_value():
    # EMA of a constant series equals that constant.
    assert indicators.ema([10] * 30, 10) == 10.0


def test_rsi_all_gains_is_100():
    closes = list(range(1, 30))  # strictly increasing
    assert indicators.rsi(closes, 14) == 100.0


def test_rsi_insufficient_data():
    assert indicators.rsi([1, 2, 3], 14) is None


def test_macd_returns_three_components():
    closes = [float(i) for i in range(1, 60)]
    m = indicators.macd(closes)
    assert set(m.keys()) == {"macd", "signal", "histogram"}
    assert m["macd"] is not None and m["signal"] is not None


def test_bollinger_band_ordering():
    closes = [10, 11, 12, 11, 10, 9, 10, 11, 12, 13, 12, 11, 10, 9, 8, 9, 10, 11, 12, 13]
    bb = indicators.bollinger_bands(closes, 20)
    assert bb["lower"] < bb["middle"] < bb["upper"]


def test_atr_positive():
    bars = _bars([float(i) for i in range(1, 40)])
    val = indicators.atr(bars, 14)
    assert val is not None and val > 0


def test_technical_snapshot_keys():
    bars = _bars([float(i) for i in range(1, 60)])
    snap = indicators.technical_snapshot(bars)
    for key in ("last_close", "sma_20", "rsi_14", "macd", "bollinger", "atr_14"):
        assert key in snap
    assert snap["n_bars"] == 59
