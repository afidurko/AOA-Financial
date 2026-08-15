"""Pure-Python pattern helpers distilled from afidurko/hft (keyianpai/hft).

Educational / research reference only. These mirror the *ideas* behind the
C++ strategies (simplearb, simplemaker, strat_MA) without CTP, ZeroMQ, or any
order path. AOA remains bar-based and cash-account; nothing here submits orders.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class Side(str, Enum):
    """Open side for a spread or mid-diff signal."""

    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


@dataclass(frozen=True)
class SpreadBands:
    """Mean-reverting bands on a mid-price differential (simplearb CalParams)."""

    mean: float
    std: float
    up: float
    down: float
    stop_loss_up: float
    stop_loss_down: float
    margin: float


@dataclass(frozen=True)
class MaCross:
    """Golden / death cross between short and long MA series (strat_MA)."""

    signal: Side
    short: float
    long: float
    short_prev: float
    long_prev: float


def mid_from_bid_ask(bid: float, ask: float) -> float:
    """Top-of-book mid."""
    return (bid + ask) / 2.0


def pair_mid_diff(
    main_bid: float,
    main_ask: float,
    hedge_bid: float,
    hedge_ask: float,
) -> float:
    """Main mid minus hedge mid — the simplearb / simplemaker spread state."""
    return mid_from_bid_ask(main_bid, main_ask) - mid_from_bid_ask(hedge_bid, hedge_ask)


def calibrate_spread_bands(
    mids: Sequence[float],
    *,
    min_train: int | None = None,
    range_width: float = 1.0,
    min_range: float = 0.0,
    fee_cost: float = 0.0,
    stop_loss_margin: float = 1.0,
) -> SpreadBands:
    """Estimate mean/std bands from a trailing window of pair mid diffs.

    Matches simplearb::CalParams: margin = max(range_width * std, min_range) + fee,
    up/down = mean ± margin, stop lines further out by stop_loss_margin * margin.
    """
    if not mids:
        raise ValueError("mids must be non-empty")
    n = len(mids)
    window = min_train if min_train is not None else n
    if window < 1 or window > n:
        raise ValueError(f"min_train={window} invalid for series length {n}")
    sample = list(mids[-window:])
    mean = sum(sample) / window
    var = sum((x - mean) ** 2 for x in sample) / window
    std = math.sqrt(var)
    margin = max(range_width * std, min_range) + fee_cost
    up = mean + margin
    down = mean - margin
    return SpreadBands(
        mean=mean,
        std=std,
        up=up,
        down=down,
        stop_loss_up=up + stop_loss_margin * margin,
        stop_loss_down=down - stop_loss_margin * margin,
        margin=margin,
    )


def open_side_from_bands(mid_diff: float, bands: SpreadBands) -> Side:
    """simplearb OpenLogicSide: sell when mid > up, buy when mid < down."""
    if mid_diff > bands.up:
        return Side.SELL
    if mid_diff < bands.down:
        return Side.BUY
    return Side.FLAT


def hit_mean(position: int, mid_diff: float, mean: float) -> bool:
    """simplearb HitMean: long exits at/above mean; short exits at/below mean."""
    if position > 0 and mid_diff >= mean:
        return True
    if position < 0 and mid_diff <= mean:
        return True
    return False


def stop_loss_hit(mid_diff: float, bands: SpreadBands) -> bool:
    """True when mid diff breaches the outer stop-loss lines."""
    return mid_diff >= bands.stop_loss_up or mid_diff <= bands.stop_loss_down


def mid_maker_side(
    main_mid: float,
    hedge_mid: float,
    *,
    up_diff: float,
    down_diff: float,
) -> Side:
    """simplemaker MidBuy / MidSell on main−hedge mid differential."""
    diff = main_mid - hedge_mid
    if diff > up_diff:
        return Side.SELL
    if diff < down_diff:
        return Side.BUY
    return Side.FLAT


def ma_cross_signal(
    short_prev: float,
    long_prev: float,
    short_now: float,
    long_now: float,
) -> MaCross:
    """strat_MA golden (buy) / death (sell) cross on two MA topics."""
    if short_prev <= long_prev and short_now > long_now:
        signal = Side.BUY
    elif short_prev >= long_prev and short_now < long_now:
        signal = Side.SELL
    else:
        signal = Side.FLAT
    return MaCross(
        signal=signal,
        short=short_now,
        long=long_now,
        short_prev=short_prev,
        long_prev=long_prev,
    )


def spread_tight_enough(
    bid: float,
    ask: float,
    *,
    max_spread: float,
) -> bool:
    """simplemaker Spread_Good: top-of-book width within max_spread."""
    return (ask - bid) <= max_spread
