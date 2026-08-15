"""Pure-Python helpers distilled from afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy.

Educational / research reference only. These mirror the *ideas* behind the SGX
A50 full-order-book notebooks (rise ratio, weighted depth, forward tradeability
labels) without sklearn, Jupyter, or any order path. AOA remains bar-based and
cash-account; nothing here submits orders.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class Side(str, Enum):
    """Suggested research side from book pressure or rise features."""

    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


@dataclass(frozen=True)
class BookLevel:
    """One price level on the bid or ask ladder."""

    price: float
    quantity: float


@dataclass(frozen=True)
class BookSnapshot:
    """Multi-level book at one instant (best level first)."""

    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    timestamp: float = 0.0


@dataclass(frozen=True)
class WeightedDepth:
    """Weighted ask/bid size and the two classic depth-ratio features."""

    weight_ask: float
    weight_bid: float
    ask_over_bid: float
    imbalance: float


@dataclass(frozen=True)
class RisePoint:
    """Percent change of a price series vs a lookback window."""

    index: int
    rise_pct: float
    window_start_index: int


def mid_from_top(bid: float, ask: float) -> float:
    """Top-of-book mid."""
    return (bid + ask) / 2.0


def rise_ratio(
    prices: Sequence[float],
    timestamps: Sequence[float],
    *,
    before_time: float,
) -> list[RisePoint]:
    """Percent rise vs the first print inside ``[t - before_time, t]``.

    Matches ``rise_ask`` in the Feature_Selection notebooks: early points
    (before the first timestamp ≥ before_time) rise vs ``prices[0]``; later
    points rise vs the earliest price whose timestamp is ≥ ``t - before_time``.
    Zero prices are replaced by the series mean (notebook behaviour).
    """
    if len(prices) != len(timestamps):
        raise ValueError("prices and timestamps must have equal length")
    if not prices:
        return []
    if before_time < 0:
        raise ValueError("before_time must be non-negative")

    cleaned: list[float] = list(prices)
    nonzero = [p for p in cleaned if p != 0]
    fill = (sum(nonzero) / len(nonzero)) if nonzero else 0.0
    cleaned = [fill if p == 0 else p for p in cleaned]

    ts = list(timestamps)
    # First index where wall-clock ≥ before_time (open warmup, notebook style).
    warmup_end = next((i for i, t in enumerate(ts) if t >= before_time), len(ts))

    out: list[RisePoint] = []
    for i, price in enumerate(cleaned):
        if i < warmup_end:
            start = 0
        else:
            target = ts[i] - before_time
            start = 0
            # Notebook uses timestamps[:i]; fall back to 0 if empty / no hit.
            for j in range(i):
                if ts[j] >= target:
                    start = j
                    break
        base = cleaned[start]
        if base == 0:
            rise = 0.0
        else:
            rise = round((price - base) / base * 100.0, 5)
        out.append(RisePoint(index=i, rise_pct=rise, window_start_index=start))
    return out


def weighted_depth(
    ask_quantities: Sequence[float],
    bid_quantities: Sequence[float],
    *,
    weights: Sequence[float] = (1.0, 1.0, 1.0),
) -> WeightedDepth:
    """Weighted multi-level depth ratios from the SGX Feature_Selection notebooks.

    ``W_AB = Weight_Ask / Weight_Bid`` and
    ``W_A_B = (Weight_Ask - Weight_Bid) / (Weight_Ask + Weight_Bid)``.
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


def depth_from_snapshot(
    book: BookSnapshot,
    *,
    levels: int = 3,
    weights: Sequence[float] = (1.0, 1.0, 1.0),
) -> WeightedDepth:
    """Weighted depth from a :class:`BookSnapshot` (best ``levels`` only)."""
    if levels < 1:
        raise ValueError("levels must be >= 1")
    asks = list(book.asks[:levels])
    bids = list(book.bids[:levels])
    while len(asks) < levels:
        asks.append(BookLevel(price=0.0, quantity=0.0))
    while len(bids) < levels:
        bids.append(BookLevel(price=0.0, quantity=0.0))
    return weighted_depth(
        [lvl.quantity for lvl in asks],
        [lvl.quantity for lvl in bids],
        weights=weights,
    )


def top_imbalance(bid_qty: float, ask_qty: float) -> float:
    """L1 size imbalance ``(ask - bid) / (ask + bid)`` (0 when empty)."""
    total = ask_qty + bid_qty
    if total == 0:
        return 0.0
    return (ask_qty - bid_qty) / total


def depth_pressure_side(
    imbalance: float,
    *,
    threshold: float = 0.15,
) -> Side:
    """Map weighted depth imbalance to a research side.

    Positive imbalance ⇒ ask-heavy ⇒ SELL pressure; negative ⇒ bid-heavy ⇒ BUY.
    Flat when ``|imbalance| < threshold``.
    """
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    if imbalance >= threshold:
        return Side.SELL
    if imbalance <= -threshold:
        return Side.BUY
    return Side.FLAT


def rise_pressure_side(
    rise_pct: float,
    *,
    threshold_pct: float = 0.05,
) -> Side:
    """Map rise-ratio percent to a research side (momentum of best ask/bid)."""
    if threshold_pct < 0:
        raise ValueError("threshold_pct must be non-negative")
    if rise_pct >= threshold_pct:
        return Side.BUY
    if rise_pct <= -threshold_pct:
        return Side.SELL
    return Side.FLAT


def combine_pressure(
    depth_side: Side,
    rise_side: Side,
) -> Side:
    """Agreeing depth + rise sides reinforce; disagreement → FLAT."""
    if depth_side is Side.FLAT:
        return rise_side
    if rise_side is Side.FLAT:
        return depth_side
    if depth_side is rise_side:
        return depth_side
    return Side.FLAT


def forward_tradeable(
    bid_prices: Sequence[float],
    ask_prices: Sequence[float],
    *,
    index: int,
    horizon: int,
) -> bool:
    """True when current bid exceeds the minimum ask over the forward window.

    Notebook label: ``bid[i] > min(ask[i : i+horizon])`` — a research
    "would have been lifted" flag for the next ``horizon`` samples (often ~10s
    of book ticks in the original SGX study). Not an execution signal.
    """
    if index < 0 or index >= len(bid_prices):
        raise IndexError("index out of range for bid_prices")
    if len(bid_prices) != len(ask_prices):
        raise ValueError("bid_prices and ask_prices must match")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    end = min(len(ask_prices), index + horizon)
    window = ask_prices[index:end]
    if not window:
        return False
    return bid_prices[index] > min(window)


def label_forward_tradeable(
    bid_prices: Sequence[float],
    ask_prices: Sequence[float],
    *,
    horizon: int,
) -> list[int]:
    """Binary labels for each index via :func:`forward_tradeable`."""
    if len(bid_prices) != len(ask_prices):
        raise ValueError("bid_prices and ask_prices must match")
    return [
        1 if forward_tradeable(bid_prices, ask_prices, index=i, horizon=horizon) else 0
        for i in range(len(bid_prices))
    ]


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
    best_bid = book.bids[0].price if book.bids else 0.0
    best_ask = book.asks[0].price if book.asks else 0.0
    bid_qty = book.bids[0].quantity if book.bids else 0.0
    ask_qty = book.asks[0].quantity if book.asks else 0.0
    feats: dict[str, float] = {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid_from_top(best_bid, best_ask) if best_bid and best_ask else 0.0,
        "spread": (best_ask - best_bid) if best_bid and best_ask else 0.0,
        "top_imbalance": top_imbalance(bid_qty, ask_qty),
        "weight_ask": depth.weight_ask,
        "weight_bid": depth.weight_bid,
        "ask_over_bid": depth.ask_over_bid
        if depth.ask_over_bid != float("inf")
        else 0.0,
        "depth_imbalance": depth.imbalance,
    }
    if prior_ask is not None and prior_ask != 0:
        feats["ask_rise_pct"] = round((best_ask - prior_ask) / prior_ask * 100.0, 5)
    if prior_bid is not None and prior_bid != 0:
        feats["bid_rise_pct"] = round((best_bid - prior_bid) / prior_bid * 100.0, 5)
    return feats


__all__ = [
    "BookLevel",
    "BookSnapshot",
    "RisePoint",
    "Side",
    "WeightedDepth",
    "combine_pressure",
    "depth_from_snapshot",
    "depth_pressure_side",
    "feature_vector",
    "forward_tradeable",
    "label_forward_tradeable",
    "mid_from_top",
    "rise_pressure_side",
    "rise_ratio",
    "top_imbalance",
    "weighted_depth",
]
