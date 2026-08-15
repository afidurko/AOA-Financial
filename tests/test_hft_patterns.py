"""Tests for HFT pattern helpers (educational reference from afidurko/hft)."""

from __future__ import annotations

import math

import pytest

from aoa.research.hft_patterns import (
    Side,
    calibrate_maker_diffs,
    calibrate_spread_bands,
    hit_mean,
    ma_cross_signal,
    mid_buy_ok,
    mid_from_bid_ask,
    mid_maker_side,
    mid_sell_ok,
    open_side_from_bands,
    pair_mid_diff,
    spread_tight_enough,
    stop_loss_hit,
)
from aoa.study.curriculum import get_card


def _pop_std(xs: list[float], mean: float) -> float:
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))


def test_pair_mid_and_bands_open_logic():
    assert mid_from_bid_ask(10.0, 10.2) == pytest.approx(10.1)
    diff = pair_mid_diff(100.0, 100.2, 50.0, 50.2)
    assert diff == pytest.approx(50.0)

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
    assert bands.stop_loss_up == pytest.approx(2.2)
    assert bands.stop_loss_down == pytest.approx(-0.2)
    assert open_side_from_bands(1.7, bands) is Side.SELL
    assert open_side_from_bands(0.3, bands) is Side.BUY
    assert open_side_from_bands(1.0, bands) is Side.FLAT
    assert open_side_from_bands(1.6, bands) is Side.FLAT  # boundary inclusive → flat
    assert open_side_from_bands(0.4, bands) is Side.FLAT


def test_calibrate_uses_trailing_window_and_std():
    series = [0.0, 0.0, 0.0, 0.0, 2.0, 4.0, 6.0, 8.0]
    bands = calibrate_spread_bands(series, min_train=4, range_width=1.0, min_range=0.0)
    assert bands.mean == pytest.approx(5.0)
    assert bands.std == pytest.approx(_pop_std([2.0, 4.0, 6.0, 8.0], 5.0))


def test_stop_loss_is_position_asymmetric():
    bands = calibrate_spread_bands(
        [1.0, 1.0, 1.0, 1.0],
        min_train=4,
        min_range=1.0,
        fee_cost=0.0,
        stop_loss_margin=1.0,
    )
    # mean=1, margin=1 → down=0, up=2, stop_down=-1, stop_up=3
    assert bands.stop_loss_down == pytest.approx(-1.0)
    assert bands.stop_loss_up == pytest.approx(3.0)
    assert stop_loss_hit(1, -1.1, bands)  # long stops below down line
    assert not stop_loss_hit(1, 3.1, bands)  # long ignores up line
    assert stop_loss_hit(-1, 3.1, bands)  # short stops above up line
    assert not stop_loss_hit(-1, -1.1, bands)
    assert not stop_loss_hit(0, -1.1, bands)
    assert not stop_loss_hit(1, -1.0, bands)  # strict < like C++


def test_zero_margin_rejected():
    with pytest.raises(ValueError, match="margin collapsed"):
        calibrate_spread_bands([1.0, 1.0, 1.0], min_range=0.0, fee_cost=0.0)


def test_hit_mean_and_maker_side():
    assert hit_mean(1, 1.0, 1.0)
    assert hit_mean(-1, -1.0, 0.0)
    assert not hit_mean(1, 0.5, 1.0)
    assert mid_maker_side(10.0, 9.0, up_diff=0.5, down_diff=-0.5) is Side.SELL
    assert mid_maker_side(9.0, 10.0, up_diff=0.5, down_diff=-0.5) is Side.BUY
    assert mid_maker_side(10.0, 10.0, up_diff=0.5, down_diff=-0.5) is Side.FLAT


def test_maker_quote_gates_and_calibrate():
    # MidBuy false when diff > up; MidSell false when diff < down
    assert mid_buy_ok(10.0, 9.0, up_diff=1.5)  # diff=1.0 <= 1.5
    assert not mid_buy_ok(10.0, 9.0, up_diff=0.5)  # diff=1.0 > 0.5
    assert mid_sell_ok(10.0, 9.0, down_diff=0.5)  # diff=1.0 >= 0.5
    assert not mid_sell_ok(9.0, 10.0, down_diff=-0.5)  # diff=-1.0 < -0.5

    diffs = calibrate_maker_diffs([0.0, 2.0, 4.0, 6.0], min_train=4)
    assert diffs.mean == pytest.approx(3.0)
    assert diffs.std == pytest.approx(_pop_std([0.0, 2.0, 4.0, 6.0], 3.0))
    assert diffs.up_diff == pytest.approx(diffs.mean + diffs.std)
    assert diffs.down_diff == pytest.approx(diffs.mean - diffs.std)


def test_ma_cross_and_spread_gate():
    golden = ma_cross_signal(9.0, 10.0, 11.0, 10.5)
    assert golden.signal is Side.BUY
    death = ma_cross_signal(11.0, 10.0, 9.0, 10.0)
    assert death.signal is Side.SELL
    # Equal prev must not fire (strat_MA uses strict inequalities)
    assert ma_cross_signal(10.0, 10.0, 11.0, 10.5).signal is Side.FLAT
    assert ma_cross_signal(11.0, 10.0, 12.0, 10.5).signal is Side.FLAT
    assert spread_tight_enough(10.0, 10.05, max_spread=0.1)
    assert not spread_tight_enough(10.0, 10.5, max_spread=0.1)
    assert not spread_tight_enough(10.5, 10.0, max_spread=1.0)  # crossed book


def test_calibrate_rejects_bad_input():
    with pytest.raises(ValueError):
        calibrate_spread_bands([])
    with pytest.raises(ValueError):
        calibrate_spread_bands([1.0, 2.0], min_train=5)
    with pytest.raises(ValueError):
        calibrate_maker_diffs([])


def test_bridge_hft_spread_card_resolves():
    card = get_card("bridge-hft-spread")
    assert card is not None
    assert get_card("bridge-ou-meanrev") is not None
    for bid in card.bridges:
        assert get_card(bid) is not None
