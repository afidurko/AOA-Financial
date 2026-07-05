"""Moomoo/Futu symbol helpers for the OpenAPI."""

from __future__ import annotations


def to_moomoo_code(symbol: str, *, market: str = "US") -> str:
    """Map ``AAPL`` → ``US.AAPL`` (pass through if already prefixed)."""
    sym = symbol.strip().upper()
    if not sym:
        return sym
    if "." in sym:
        return sym
    return f"{market}.{sym}"


def from_moomoo_code(code: str) -> str:
    """Map ``US.AAPL`` → ``AAPL``."""
    text = code.strip().upper()
    if "." in text:
        return text.split(".", 1)[1]
    return text
