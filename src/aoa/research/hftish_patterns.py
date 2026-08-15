"""Pure-Python pattern helpers distilled from afidurko/example-hftish.

Educational / research reference only. These mirror the *ideas* behind Alpaca's
order-book imbalance tick-taker (Quote level changes, size imbalance, trade
follow timing) without Alpaca streaming, Polygon, or any order path. AOA remains
bar-based and cash-account; nothing here submits orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Side(str, Enum):
    """Suggested trade side from imbalance / follow logic."""

    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


@dataclass(frozen=True)
class TopOfBook:
    """One top-of-book quote snapshot (bid/ask price + size)."""

    bid: float
    ask: float
    bid_size: float
    ask_size: float
    timestamp_ms: float = 0.0


@dataclass(frozen=True)
class LevelChange:
    """A 1¢ spread level change between two consecutive penny-spread quotes."""

    prev: TopOfBook
    current: TopOfBook
    prev_spread: float
    spread: float


@dataclass(frozen=True)
class FollowSignal:
    """Whether a print is eligible to follow after a level change."""

    side: Side
    reason: str
    imbalance_ratio: float


def spread(bid: float, ask: float) -> float:
    """Top-of-book width."""
    return ask - bid


def is_penny_spread(bid: float, ask: float, *, eps: float = 1e-9) -> bool:
    """True when ask − bid rounds to exactly one penny (tick_taker gate)."""
    return abs(round(ask - bid, 2) - 0.01) <= eps


def detect_level_change(
    prev: TopOfBook,
    current: TopOfBook,
) -> LevelChange | None:
    """Return a LevelChange when both bid and ask move and the new spread is 1¢.

    Matches tick_taker.Quote.update: both sides must change and the new spread
    must be a one-penny market. Caller decides whether prev was also a penny
    spread (reset / arm for trading).
    """
    if prev.bid == current.bid or prev.ask == current.ask:
        return None
    if not is_penny_spread(current.bid, current.ask):
        return None
    return LevelChange(
        prev=prev,
        current=current,
        prev_spread=round(spread(prev.bid, prev.ask), 3),
        spread=round(spread(current.bid, current.ask), 3),
    )


def arms_after_level_change(change: LevelChange) -> bool:
    """True when the prior spread was also 1¢ — tick_taker resets traded=False."""
    return abs(change.prev_spread - 0.01) < 1e-9


def imbalance_ratio(bid_size: float, ask_size: float) -> float:
    """Bid size / ask size (∞ when ask_size is 0 and bid_size > 0)."""
    if ask_size <= 0:
        return float("inf") if bid_size > 0 else 0.0
    return bid_size / ask_size


def book_imbalance_side(
    bid_size: float,
    ask_size: float,
    *,
    threshold: float = 1.8,
) -> Side:
    """Order-book imbalance direction used by tick_taker.

    Buy pressure when bid_size > threshold * ask_size; sell pressure when
    ask_size > threshold * bid_size; otherwise flat.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    if bid_size > ask_size * threshold:
        return Side.BUY
    if ask_size > bid_size * threshold:
        return Side.SELL
    return Side.FLAT


def trade_follows_quote(
    quote_timestamp_ms: float,
    trade_timestamp_ms: float,
    *,
    min_lag_ms: float = 50.0,
) -> bool:
    """True when the trade arrives at least min_lag_ms after the level change.

    tick_taker ignores prints within 50ms of the quote update (stale level).
    """
    return trade_timestamp_ms > quote_timestamp_ms + min_lag_ms


def position_allows_buy(
    total_shares: int,
    pending_buy: int,
    *,
    max_shares: int,
    lot: int = 100,
) -> bool:
    """Room for another buy lot without exceeding max_shares (tick_taker gate)."""
    if lot <= 0 or max_shares < lot:
        raise ValueError("max_shares must be >= lot > 0")
    return (total_shares + pending_buy) < max_shares - lot


def position_allows_sell(
    total_shares: int,
    pending_sell: int,
    *,
    lot: int = 100,
) -> bool:
    """Enough filled inventory (net of pending sells) for another sell lot."""
    if lot <= 0:
        raise ValueError("lot must be positive")
    return (total_shares - pending_sell) >= lot


def follow_print_signal(
    quote: TopOfBook,
    *,
    trade_price: float,
    trade_size: float,
    trade_timestamp_ms: float,
    armed: bool,
    total_shares: int = 0,
    pending_buy: int = 0,
    pending_sell: int = 0,
    max_shares: int = 500,
    lot: int = 100,
    imbalance_threshold: float = 1.8,
    min_trade_size: float = 100.0,
    min_lag_ms: float = 50.0,
) -> FollowSignal:
    """Research-only follow decision after a level change (tick_taker on_trade).

    Returns BUY when a large print hits the ask with bid-heavy book and room to
    add; SELL when a large print hits the bid with ask-heavy book and inventory.
    Never places orders — signal / reason only.
    """
    ratio = imbalance_ratio(quote.bid_size, quote.ask_size)
    if not armed:
        return FollowSignal(Side.FLAT, "not_armed", ratio)
    if not trade_follows_quote(
        quote.timestamp_ms, trade_timestamp_ms, min_lag_ms=min_lag_ms
    ):
        return FollowSignal(Side.FLAT, "trade_too_soon", ratio)
    if trade_size < min_trade_size:
        return FollowSignal(Side.FLAT, "trade_too_small", ratio)

    pressure = book_imbalance_side(
        quote.bid_size, quote.ask_size, threshold=imbalance_threshold
    )
    if trade_price == quote.ask and pressure is Side.BUY:
        if position_allows_buy(
            total_shares, pending_buy, max_shares=max_shares, lot=lot
        ):
            return FollowSignal(Side.BUY, "follow_ask_imbalance", ratio)
        return FollowSignal(Side.FLAT, "buy_capacity", ratio)
    if trade_price == quote.bid and pressure is Side.SELL:
        if position_allows_sell(total_shares, pending_sell, lot=lot):
            return FollowSignal(Side.SELL, "follow_bid_imbalance", ratio)
        return FollowSignal(Side.FLAT, "sell_capacity", ratio)
    return FollowSignal(Side.FLAT, "no_follow", ratio)
