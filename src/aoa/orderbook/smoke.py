"""Synthetic LOB smoke: add / update / cancel without brokerage I/O."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from aoa.orderbook.vendor import LimitOrderBook, Order


@dataclass(frozen=True)
class BookSmokeResult:
    """Summary of a synthetic limit-order-book exercise."""

    ok: bool
    best_bid: float | None
    best_ask: float | None
    bid_volume: float | None
    ask_volume: float | None
    order_count: int
    levels: int
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_book_smoke(*, mid: float = 100.0, size: int = 5) -> BookSmokeResult:
    """Exercise add → update → cancel on a fresh book."""
    book = LimitOrderBook()
    bid_px = mid - 1.0
    ask_px = mid + 1.0

    book.process(Order(uid=1, is_bid=True, size=size, price=bid_px))
    book.process(Order(uid=2, is_bid=False, size=size, price=ask_px))
    # Second bid at same level (queue)
    book.process(Order(uid=3, is_bid=True, size=size, price=bid_px))
    # Update first bid size down
    book.process(Order(uid=1, is_bid=True, size=size - 1, price=bid_px))
    # Cancel second bid
    book.process(Order(uid=3, is_bid=True, size=0, price=bid_px))

    best_bid = float(book.best_bid.price) if book.best_bid else None
    best_ask = float(book.best_ask.price) if book.best_ask else None
    bid_vol = float(book.best_bid.volume) if book.best_bid else None
    ask_vol = float(book.best_ask.volume) if book.best_ask else None
    order_count = len(book._orders)  # noqa: SLF001 — intentional smoke introspection
    levels = len(book._price_levels)  # noqa: SLF001

    ok = (
        best_bid == bid_px
        and best_ask == ask_px
        and bid_vol == bid_px * (size - 1)
        and ask_vol == ask_px * size
        and order_count == 2
        and levels == 2
    )
    return BookSmokeResult(
        ok=ok,
        best_bid=best_bid,
        best_ask=best_ask,
        bid_volume=bid_vol,
        ask_volume=ask_vol,
        order_count=order_count,
        levels=levels,
        detail="add/update/cancel on vendored LimitOrderBook" if ok else "book smoke failed",
    )
