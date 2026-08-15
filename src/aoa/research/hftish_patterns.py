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


@dataclass(frozen=True)
class BookDiagnosis:
    """Deterministic top-of-book imbalance note for Julie / Morgan prompts."""

    available: bool
    side: Side
    ratio: float | None
    bid: float | None = None
    ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    spread: float | None = None
    penny_spread: bool = False
    note: str = ""
    signal: str | None = None

    def to_context(self) -> dict[str, object]:
        return {
            "available": self.available,
            "side": self.side.value,
            "ratio": self.ratio,
            "bid": self.bid,
            "ask": self.ask,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "spread": self.spread,
            "penny_spread": self.penny_spread,
            "note": self.note,
            "signal": self.signal,
        }


def diagnose_quote_book(
    bid: float,
    ask: float,
    bid_size: float,
    ask_size: float,
    *,
    threshold: float = 1.8,
) -> BookDiagnosis:
    """Research-only book pressure from a live AOA Quote (sizes may be zero)."""
    if bid <= 0 or ask <= 0:
        return BookDiagnosis(
            available=False,
            side=Side.FLAT,
            ratio=None,
            note="No usable bid/ask for book diagnosis.",
        )
    if bid_size <= 0 and ask_size <= 0:
        return BookDiagnosis(
            available=False,
            side=Side.FLAT,
            ratio=None,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            spread=round(spread(bid, ask), 4),
            penny_spread=is_penny_spread(bid, ask),
            note="Quote sizes unavailable — skip imbalance gate.",
        )
    ratio = imbalance_ratio(bid_size, ask_size)
    side = book_imbalance_side(bid_size, ask_size, threshold=threshold)
    pennies = is_penny_spread(bid, ask)
    if side is Side.BUY:
        note = (
            f"Bid-heavy book ({bid_size:g} vs {ask_size:g}, ratio={ratio:.2f}≥"
            f"{threshold}); tick_taker-style buy pressure."
        )
        signal = f"book_imbalance:buy ratio={ratio:.2f}"
    elif side is Side.SELL:
        inv = (1.0 / ratio) if ratio not in (0.0, float("inf")) else float("inf")
        note = (
            f"Ask-heavy book ({ask_size:g} vs {bid_size:g}, ask/bid={inv:.2f}≥"
            f"{threshold}); tick_taker-style sell pressure."
        )
        signal = f"book_imbalance:sell ratio={ratio:.2f}"
    else:
        note = (
            f"Balanced book ({bid_size:g}/{ask_size:g}, ratio={ratio:.2f}); "
            "no tick_taker imbalance signal."
        )
        signal = None
    if pennies:
        note = f"{note} Spread is 1¢."
    return BookDiagnosis(
        available=True,
        side=side,
        ratio=None if ratio == float("inf") else round(ratio, 4),
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        spread=round(spread(bid, ask), 4),
        penny_spread=pennies,
        note=note,
        signal=signal,
    )


def diagnose_snapshot_quote(quote: object, *, threshold: float = 1.8) -> BookDiagnosis:
    """Accept an AOA ``Quote`` (or any object with bid/ask/size attrs)."""
    bid = float(getattr(quote, "bid", 0.0) or 0.0)
    ask = float(getattr(quote, "ask", 0.0) or 0.0)
    bid_size = float(getattr(quote, "bid_size", 0.0) or 0.0)
    ask_size = float(getattr(quote, "ask_size", 0.0) or 0.0)
    return diagnose_quote_book(
        bid, ask, bid_size, ask_size, threshold=threshold
    )


def synthetic_smoke(*, seed: int = 7) -> dict[str, object]:
    """Offline smoke for ``aoa hftish smoke`` — no broker, no orders."""
    del seed  # reserved for future RNG scenarios; keep signature stable
    prev = TopOfBook(10.00, 10.01, bid_size=200, ask_size=100, timestamp_ms=0.0)
    curr = TopOfBook(10.01, 10.02, bid_size=500, ask_size=100, timestamp_ms=100.0)
    change = detect_level_change(prev, curr)
    diag = diagnose_quote_book(curr.bid, curr.ask, curr.bid_size, curr.ask_size)
    follow = follow_print_signal(
        curr,
        trade_price=curr.ask,
        trade_size=100,
        trade_timestamp_ms=200.0,
        armed=bool(change and arms_after_level_change(change)),
        total_shares=0,
        max_shares=500,
    )
    return {
        "ok": follow.side is Side.BUY and diag.side is Side.BUY,
        "level_change": change is not None,
        "armed": bool(change and arms_after_level_change(change)),
        "diagnosis": diag.to_context(),
        "follow": {"side": follow.side.value, "reason": follow.reason},
        "never_live": True,
        "module": "aoa.research.hftish_patterns",
        "companion": "example-hftish",
    }


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
