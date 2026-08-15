"""Standalone limit-order-book helpers (offline).

Wraps the vendored
`HFT-Orderbook <https://github.com/afidurko/HFT-Orderbook>`_ implementation
(WK Selph / Crypto-toolbox design) for local add/cancel/execute research.

This is **not** a live broker connector and is not wired into ``Executor``.
For tick replay with latency/queue models, see ``aoa.hftbacktest``.
"""

from __future__ import annotations

from aoa.orderbook.probe import probe_status
from aoa.orderbook.smoke import BookSmokeResult, run_book_smoke
from aoa.orderbook.vendor import LimitOrderBook, Order

HAS_ORDERBOOK = True

__all__ = [
    "HAS_ORDERBOOK",
    "BookSmokeResult",
    "LimitOrderBook",
    "Order",
    "probe_status",
    "run_book_smoke",
]
