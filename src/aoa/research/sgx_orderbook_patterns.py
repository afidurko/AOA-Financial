"""Pure-Python helpers from afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy.

Research / educational only: rise ratio, weighted depth, and forward tradeability
labels from the SGX A50 notebooks — no sklearn, Jupyter, or order path.
Works with plain level tuples or ``aoa.orderbook.LimitOrderBook`` snapshots.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class Side(str, Enum):
    """Research side from book pressure or rise features."""

    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


@dataclass(frozen=True)
class BookLevel:
    """One price level (best first when inside a snapshot)."""

    price: float
    quantity: float


@dataclass(frozen=True)
class BookSnapshot:
    """Multi-level book at one instant."""

    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    timestamp: float = 0.0


@dataclass(frozen=True)
class WeightedDepth:
    """Weighted ask/bid size and classic depth-ratio features."""

    weight_ask: float
    weight_bid: float
    ask_over_bid: float
    imbalance: float


@dataclass(frozen=True)
class RisePoint:
    """Percent change vs a lookback window."""

    index: int
    rise_pct: float
    window_start_index: int


class _LimitLevelLike(Protocol):
    price: float
    size: float


class _LimitOrderBookLike(Protocol):
    best_bid: _LimitLevelLike | None
    best_ask: _LimitLevelLike | None

    def levels(self, depth: int | None = None) -> dict[str, list[Any]]: ...


def mid_from_top(bid: float, ask: float) -> float:
    """Top-of-book mid."""
    return (bid + ask) / 2.0


def rise_ratio(
    prices: Sequence[float],
    timestamps: Sequence[float],
    *,
    before_time: float,
) -> list[RisePoint]:
    """Percent rise vs the first print in ``[t - before_time, t]``.

    Matches notebook ``rise_ask``: warmup samples (before the first timestamp
    ≥ ``before_time``) rise vs ``prices[0]``; later samples use a trailing
    window. Zero prices are replaced by the series mean. Timestamps should be
    non-decreasing.
    """
    if len(prices) != len(timestamps):
        raise ValueError("prices and timestamps must have equal length")
    if before_time < 0:
        raise ValueError("before_time must be non-negative")
    if not prices:
        return []

    nonzero = [p for p in prices if p != 0]
    fill = (sum(nonzero) / len(nonzero)) if nonzero else 0.0
    cleaned = [fill if p == 0 else float(p) for p in prices]
    ts = [float(t) for t in timestamps]
    warmup_end = next((i for i, t in enumerate(ts) if t >= before_time), len(ts))

    out: list[RisePoint] = []
    start = 0
    for i, price in enumerate(cleaned):
        if i < warmup_end:
            window_start = 0
        else:
            target = ts[i] - before_time
            while start < i and ts[start] < target:
                start += 1
            window_start = start if start < i else 0
        base = cleaned[window_start]
        rise = 0.0 if base == 0 else round((price - base) / base * 100.0, 5)
        out.append(RisePoint(index=i, rise_pct=rise, window_start_index=window_start))
    return out


def weighted_depth(
    ask_quantities: Sequence[float],
    bid_quantities: Sequence[float],
    *,
    weights: Sequence[float] = (1.0, 1.0, 1.0),
) -> WeightedDepth:
    """Weighted multi-level depth ratios (SGX Feature_Selection notebooks).

    ``ask_over_bid = W_ask / W_bid`` and
    ``imbalance = (W_ask - W_bid) / (W_ask + W_bid)``.
    """
    if len(ask_quantities) != len(bid_quantities):
        raise ValueError("ask_quantities and bid_quantities must match")
    n = len(ask_quantities)
    if n == 0:
        raise ValueError("quantities must be non-empty")
    if len(weights) < n:
        raise ValueError("weights length must be >= number of levels")

    w_ask = sum(float(weights[i]) * float(ask_quantities[i]) for i in range(n))
    w_bid = sum(float(weights[i]) * float(bid_quantities[i]) for i in range(n))
    if w_bid == 0:
        ask_over_bid = float("inf") if w_ask > 0 else 0.0
    else:
        ask_over_bid = w_ask / w_bid
    denom = w_ask + w_bid
    imbalance = 0.0 if denom == 0 else (w_ask - w_bid) / denom
    return WeightedDepth(
        weight_ask=w_ask,
        weight_bid=w_bid,
        ask_over_bid=ask_over_bid,
        imbalance=imbalance,
    )


def _pad_levels(
    levels: Sequence[BookLevel],
    count: int,
) -> list[BookLevel]:
    out = list(levels[:count])
    while len(out) < count:
        out.append(BookLevel(price=0.0, quantity=0.0))
    return out


def depth_from_snapshot(
    book: BookSnapshot,
    *,
    levels: int = 3,
    weights: Sequence[float] = (1.0, 1.0, 1.0),
) -> WeightedDepth:
    """Weighted depth from a :class:`BookSnapshot` (best ``levels`` only)."""
    if levels < 1:
        raise ValueError("levels must be >= 1")
    asks = _pad_levels(book.asks, levels)
    bids = _pad_levels(book.bids, levels)
    return weighted_depth(
        [lvl.quantity for lvl in asks],
        [lvl.quantity for lvl in bids],
        weights=weights,
    )


def snapshot_from_limit_order_book(
    book: _LimitOrderBookLike,
    *,
    levels: int = 3,
    timestamp: float = 0.0,
) -> BookSnapshot:
    """Convert ``aoa.orderbook.LimitOrderBook`` (or duck-type) → :class:`BookSnapshot`.

    Uses aggregate ``LimitLevel.size`` (shares), not notional ``volume``.
    """
    if levels < 1:
        raise ValueError("levels must be >= 1")
    if book.best_bid is None and book.best_ask is None:
        return BookSnapshot(bids=(), asks=(), timestamp=timestamp)
    if book.best_bid is None or book.best_ask is None:
        bids: tuple[BookLevel, ...] = ()
        asks: tuple[BookLevel, ...] = ()
        if book.best_bid is not None:
            bids = (BookLevel(float(book.best_bid.price), float(book.best_bid.size)),)
        if book.best_ask is not None:
            asks = (BookLevel(float(book.best_ask.price), float(book.best_ask.size)),)
        return BookSnapshot(bids=bids, asks=asks, timestamp=timestamp)

    raw = book.levels(levels)
    bids = tuple(
        BookLevel(float(lvl.price), float(lvl.size)) for lvl in raw.get("bids", [])[:levels]
    )
    asks = tuple(
        BookLevel(float(lvl.price), float(lvl.size)) for lvl in raw.get("asks", [])[:levels]
    )
    return BookSnapshot(bids=bids, asks=asks, timestamp=timestamp)


def top_imbalance(bid_qty: float, ask_qty: float) -> float:
    """L1 size imbalance ``(ask - bid) / (ask + bid)`` (0 when empty)."""
    total = ask_qty + bid_qty
    if total == 0:
        return 0.0
    return (ask_qty - bid_qty) / total


def depth_pressure_side(imbalance: float, *, threshold: float = 0.15) -> Side:
    """Ask-heavy (positive) → SELL; bid-heavy → BUY; else FLAT."""
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    if imbalance >= threshold:
        return Side.SELL
    if imbalance <= -threshold:
        return Side.BUY
    return Side.FLAT


def rise_pressure_side(rise_pct: float, *, threshold_pct: float = 0.05) -> Side:
    """Map rise-ratio percent to a research side."""
    if threshold_pct < 0:
        raise ValueError("threshold_pct must be non-negative")
    if rise_pct >= threshold_pct:
        return Side.BUY
    if rise_pct <= -threshold_pct:
        return Side.SELL
    return Side.FLAT


def combine_pressure(depth_side: Side, rise_side: Side) -> Side:
    """Agreeing sides reinforce; disagreement → FLAT."""
    if depth_side is Side.FLAT:
        return rise_side
    if rise_side is Side.FLAT:
        return depth_side
    return depth_side if depth_side is rise_side else Side.FLAT


def forward_tradeable(
    bid_prices: Sequence[float],
    ask_prices: Sequence[float],
    *,
    index: int,
    horizon: int,
) -> bool:
    """True when ``bid[i] > min(ask[i : i+horizon])`` (notebook research label)."""
    if index < 0 or index >= len(bid_prices):
        raise IndexError("index out of range for bid_prices")
    if len(bid_prices) != len(ask_prices):
        raise ValueError("bid_prices and ask_prices must match")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    window = ask_prices[index : index + horizon]
    return bool(window) and bid_prices[index] > min(window)


def label_forward_tradeable(
    bid_prices: Sequence[float],
    ask_prices: Sequence[float],
    *,
    horizon: int,
) -> list[int]:
    """Binary forward-tradeable labels for each index."""
    if len(bid_prices) != len(ask_prices):
        raise ValueError("bid_prices and ask_prices must match")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    n = len(bid_prices)
    out: list[int] = []
    for i in range(n):
        window = ask_prices[i : i + horizon]
        out.append(1 if window and bid_prices[i] > min(window) else 0)
    return out


def feature_vector(
    book: BookSnapshot,
    *,
    prior_ask: float | None = None,
    prior_bid: float | None = None,
    levels: int = 3,
    weights: Sequence[float] = (1.0, 1.0, 1.0),
) -> dict[str, float]:
    """Compact research feature dict from one book snapshot (+ optional priors)."""
    depth = depth_from_snapshot(book, levels=levels, weights=weights)
    has_top = bool(book.bids) and bool(book.asks)
    best_bid = book.bids[0].price if book.bids else 0.0
    best_ask = book.asks[0].price if book.asks else 0.0
    bid_qty = book.bids[0].quantity if book.bids else 0.0
    ask_qty = book.asks[0].quantity if book.asks else 0.0
    feats: dict[str, float] = {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid_from_top(best_bid, best_ask) if has_top else 0.0,
        "spread": (best_ask - best_bid) if has_top else 0.0,
        "top_imbalance": top_imbalance(bid_qty, ask_qty),
        "weight_ask": depth.weight_ask,
        "weight_bid": depth.weight_bid,
        "depth_imbalance": depth.imbalance,
    }
    if depth.ask_over_bid != float("inf"):
        feats["ask_over_bid"] = depth.ask_over_bid
    if prior_ask is not None and prior_ask != 0:
        feats["ask_rise_pct"] = round((best_ask - prior_ask) / prior_ask * 100.0, 5)
    if prior_bid is not None and prior_bid != 0:
        feats["bid_rise_pct"] = round((best_bid - prior_bid) / prior_bid * 100.0, 5)
    return feats
