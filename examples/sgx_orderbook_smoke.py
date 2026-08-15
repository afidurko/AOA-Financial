#!/usr/bin/env python3
"""Offline smoke: vendored LOB → SGX rise/depth features (no brokerage)."""

from __future__ import annotations

from aoa.orderbook import LimitOrderBook, Order
from aoa.research.sgx_orderbook_patterns import (
    combine_pressure,
    depth_from_snapshot,
    depth_pressure_side,
    feature_vector,
    rise_pressure_side,
    snapshot_from_limit_order_book,
)


def main() -> None:
    book = LimitOrderBook()
    # Three-level synthetic book
    book.process(Order(uid=1, is_bid=True, size=40, price=99.0))
    book.process(Order(uid=2, is_bid=True, size=20, price=98.0))
    book.process(Order(uid=3, is_bid=True, size=10, price=97.0))
    book.process(Order(uid=4, is_bid=False, size=30, price=100.0))
    book.process(Order(uid=5, is_bid=False, size=25, price=101.0))
    book.process(Order(uid=6, is_bid=False, size=15, price=102.0))

    snap = snapshot_from_limit_order_book(book, levels=3, timestamp=1.0)
    depth = depth_from_snapshot(snap)
    feats = feature_vector(snap, prior_ask=99.5, prior_bid=98.5)
    side = combine_pressure(
        depth_pressure_side(depth.imbalance),
        rise_pressure_side(feats.get("ask_rise_pct", 0.0)),
    )
    print(
        {
            "depth_imbalance": depth.imbalance,
            "ask_over_bid": depth.ask_over_bid,
            "features": feats,
            "research_side": side.value,
            "offline_only": True,
        }
    )


if __name__ == "__main__":
    main()
