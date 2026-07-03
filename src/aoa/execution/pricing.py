"""Order pricing helpers."""

from __future__ import annotations

from aoa.brokerage.models import Side


def marketable_limit(price: float, side: Side) -> float:
    """A protective limit ~1% through the mid to improve fill odds without chasing."""
    pad = 1.01 if side is Side.BUY else 0.99
    return round(price * pad, 2)
