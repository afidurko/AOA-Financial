"""Tests for HFT pattern helpers (educational reference from afidurko/hft)."""

from __future__ import annotations

import math

import pytest

from aoa.research.hft_patterns import (
    Side,
    calibrate_spread_bands,
    hit_mean,
    ma_cross_signal,
    mid_from_bid_ask,
    mid_maker_side,
    open_side_from_bands,
    pair_mid_diff,
    spread_tight_enough,
    stop_loss_hit,
)


def _pop_std(xs: list[float], mean: float) -> float:
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))


def test_pair_mid_and_bands_open_logic():
    assert mid_from_bid_ask(10.0, 10.2) == pytest.approx(10.1)
    diff = pair_mid_diff(100.0, 100.2, 50.0, 50.2)
    assert diff == pytest.approx(50.0)

    # Constant series → std 0 → margin = min_range + fee
    bands = calibrate_spread_bands(
        [1.0, 1.0, 1.0, 1.0],
        min_train=4,
        range_width=2.0,
        min_range=0.5,
        fee_cost=0.1,
        stop_loss_margin=1.0,
    )
    assert bands.mean == pytest.approx(1.0)
    assert bands.std == pytest.approx(0.0)
    assert bands.margin == pytest.approx(0.6)
    assert bands.up == pytest.approx(1.6)
    assert bands.down == pytest.approx(0.4)
    assert open_side_from_bands(1.7, bands) is Side.SELL
    assert open_side_from_bands(0.3, bands) is Side.BUY
    assert open_side_from_bands(1.0, bands) is Side.FLAT
    assert stop_loss_hit(2.3, bands)
    assert not stop_loss_hit(1.0, bands)


def test_calibrate_uses_trailing_window_and_std():
    series = [0.0, 0.0, 0.0, 0.0, 2.0, 4.0, 6.0, 8.0]
    bands = calibrate_spread_bands(series, min_train=4, range_width=1.0, min_range=0.0)
    assert bands.mean == pytest.approx(5.0)
    assert bands.std == pytest.approx(_pop_std([2.0, 4.0, 6.0, 8.0], 5.0))


def test_hit_mean_and_maker_side():
    assert hit_mean(1, 1.0, 1.0)
    assert hit_mean(-1, -1.0, 0.0)
    assert not hit_mean(1, 0.5, 1.0)
    assert mid_maker_side(10.0, 9.0, up_diff=0.5, down_diff=-0.5) is Side.SELL
    assert mid_maker_side(9.0, 10.0, up_diff=0.5, down_diff=-0.5) is Side.BUY
    assert mid_maker_side(10.0, 10.0, up_diff=0.5, down_diff=-0.5) is Side.FLAT


def test_ma_cross_and_spread_gate():
    golden = ma_cross_signal(9.0, 10.0, 11.0, 10.5)
    assert golden.signal is Side.BUY
    death = ma_cross_signal(11.0, 10.0, 9.0, 10.0)
    assert death.signal is Side.SELL
    flat = ma_cross_signal(11.0, 10.0, 12.0, 10.5)
    assert flat.signal is Side.FLAT
    assert spread_tight_enough(10.0, 10.05, max_spread=0.1)
    assert not spread_tight_enough(10.0, 10.5, max_spread=0.1)


def test_calibrate_rejects_bad_input():
    with pytest.raises(ValueError):
        calibrate_spread_bands([])
    with pytest.raises(ValueError):
        calibrate_spread_bands([1.0, 2.0], min_train=5)
