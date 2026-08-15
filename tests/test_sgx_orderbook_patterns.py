"""Tests for SGX order-book research pattern helpers."""

from __future__ import annotations

import math

import pytest

from aoa.research.sgx_orderbook_patterns import (
    BookLevel,
    BookSnapshot,
    Side,
    combine_pressure,
    depth_from_snapshot,
    depth_pressure_side,
    feature_vector,
    forward_tradeable,
    label_forward_tradeable,
    mid_from_top,
    rise_pressure_side,
    rise_ratio,
    top_imbalance,
    weighted_depth,
)


def test_mid_and_top_imbalance():
    assert mid_from_top(100.0, 102.0) == 101.0
    assert top_imbalance(40.0, 60.0) == pytest.approx(0.2)
    assert top_imbalance(0.0, 0.0) == 0.0


def test_weighted_depth_ratios():
    depth = weighted_depth([10, 20, 30], [30, 20, 10], weights=(1.0, 1.0, 1.0))
    assert depth.weight_ask == 60.0
    assert depth.weight_bid == 60.0
    assert depth.ask_over_bid == pytest.approx(1.0)
    assert depth.imbalance == pytest.approx(0.0)

    ask_heavy = weighted_depth([50, 0, 0], [10, 0, 0])
    assert ask_heavy.ask_over_bid == pytest.approx(5.0)
    assert ask_heavy.imbalance == pytest.approx(40.0 / 60.0)


def test_weighted_depth_zero_bid():
    depth = weighted_depth([5.0], [0.0])
    assert depth.ask_over_bid == float("inf")
    assert depth.imbalance == pytest.approx(1.0)


def test_depth_from_snapshot_pads_levels():
    book = BookSnapshot(
        bids=(BookLevel(99.0, 10.0),),
        asks=(BookLevel(100.0, 20.0), BookLevel(101.0, 5.0)),
    )
    depth = depth_from_snapshot(book, levels=3, weights=(1.0, 1.0, 1.0))
    assert depth.weight_ask == 25.0
    assert depth.weight_bid == 10.0


def test_rise_ratio_warmup_then_window():
    # timestamps in seconds; before_time=10 → warmup uses prices[0] as base
    prices = [100.0, 101.0, 102.0, 103.0, 110.0]
    ts = [0.0, 5.0, 10.0, 15.0, 20.0]
    points = rise_ratio(prices, ts, before_time=10.0)
    assert len(points) == 5
    # i=0,1 still in warmup (warmup_end = index of ts>=10 → 2)
    assert points[0].rise_pct == 0.0
    assert points[1].rise_pct == pytest.approx(1.0)
    # i=2: window start at ts>=0 → 0
    assert points[2].window_start_index == 0
    assert points[2].rise_pct == pytest.approx(2.0)
    # i=4 (t=20): window start at first ts >= 10 → index 2 (102)
    assert points[4].window_start_index == 2
    assert points[4].rise_pct == pytest.approx(round((110 - 102) / 102 * 100, 5))


def test_rise_ratio_replaces_zero_with_mean():
    points = rise_ratio([0.0, 100.0], [0.0, 1.0], before_time=0.0)
    # mean of nonzero = 100; first becomes 100 → rise 0; second rise 0 vs base at t-0
    assert points[0].rise_pct == 0.0


def test_pressure_sides_and_combine():
    assert depth_pressure_side(0.2, threshold=0.15) is Side.SELL
    assert depth_pressure_side(-0.2, threshold=0.15) is Side.BUY
    assert depth_pressure_side(0.01, threshold=0.15) is Side.FLAT
    assert rise_pressure_side(0.1, threshold_pct=0.05) is Side.BUY
    assert rise_pressure_side(-0.1, threshold_pct=0.05) is Side.SELL
    assert combine_pressure(Side.BUY, Side.BUY) is Side.BUY
    assert combine_pressure(Side.BUY, Side.SELL) is Side.FLAT
    assert combine_pressure(Side.FLAT, Side.SELL) is Side.SELL


def test_forward_tradeable_label():
    bids = [10.0, 10.0, 10.0, 9.0]
    asks = [11.0, 10.5, 9.5, 10.0]
    # index 0: bid 10 > min(11, 10.5) = 10.5? No
    assert forward_tradeable(bids, asks, index=0, horizon=2) is False
    # index 0 horizon 3: min(11,10.5,9.5)=9.5 → True
    assert forward_tradeable(bids, asks, index=0, horizon=3) is True
    labels = label_forward_tradeable(bids, asks, horizon=2)
    assert labels == [0, 1, 1, 0]


def test_feature_vector_keys():
    book = BookSnapshot(
        bids=(BookLevel(99.0, 40.0), BookLevel(98.0, 20.0), BookLevel(97.0, 10.0)),
        asks=(BookLevel(100.0, 30.0), BookLevel(101.0, 20.0), BookLevel(102.0, 10.0)),
        timestamp=1.0,
    )
    feats = feature_vector(book, prior_ask=99.0, prior_bid=98.0)
    assert feats["best_bid"] == 99.0
    assert feats["best_ask"] == 100.0
    assert feats["spread"] == 1.0
    assert "depth_imbalance" in feats
    assert "ask_rise_pct" in feats
    assert "bid_rise_pct" in feats
    assert math.isfinite(feats["ask_over_bid"])


def test_invalid_inputs():
    with pytest.raises(ValueError):
        rise_ratio([1.0], [1.0, 2.0], before_time=1.0)
    with pytest.raises(ValueError):
        weighted_depth([1.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        depth_pressure_side(0.0, threshold=-1.0)
    with pytest.raises(IndexError):
        forward_tradeable([1.0], [1.0], index=5, horizon=1)
