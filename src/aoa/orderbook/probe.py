"""Status probe for the vendored HFT-Orderbook lane."""

from __future__ import annotations

from typing import Any


def probe_status() -> dict[str, Any]:
    """Return a JSON-serializable status dict for ``aoa hft book-smoke`` / status."""
    try:
        from aoa.orderbook.vendor import LimitOrderBook, Order

        book = LimitOrderBook()
        book.process(Order(uid=1, is_bid=True, size=1, price=100))
        book.process(Order(uid=2, is_bid=False, size=1, price=101))
        ok = book.best_bid is not None and book.best_ask is not None
    except Exception as exc:  # pragma: no cover - vendor import failure
        return {
            "installed": False,
            "ok": False,
            "error": str(exc),
            "upstream": "https://github.com/afidurko/HFT-Orderbook",
            "offline_only": True,
            "implementation": "vendored",
        }

    return {
        "installed": True,
        "ok": ok,
        "engine": "LimitOrderBook",
        "implementation": "vendored",
        "upstream": "https://github.com/afidurko/HFT-Orderbook",
        "parent": "https://github.com/Crypto-toolbox/HFT-Orderbook",
        "offline_only": True,
        "hint": "aoa hft book-smoke",
    }
