"""Shared Alpaca configuration constants."""

from __future__ import annotations

VALID_ALPACA_DATA_FEEDS = frozenset({"sip", "iex", "boats", "otc"})
VALID_ALPACA_BAR_ADJUSTMENTS = frozenset({"raw", "split", "dividend", "all", "spin-off"})
