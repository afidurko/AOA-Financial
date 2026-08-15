"""Avellaneda–Stoikov reservation price and optimal quotes (research math).

Formulas follow Avellaneda & Stoikov, *High-frequency trading in a limit order
book* (Quantitative Finance, 2008), as implemented in
https://github.com/afidurko/avellaneda-stoikov — pure Python, no broker I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ASParams:
    """Market-making control parameters."""

    gamma: float = 0.1
    """Risk aversion (→0 aggressive, larger → tighter inventory penalty)."""
    sigma: float = 2.0
    """Mid-price volatility (absolute, same units as price)."""
    k: float = 1.5
    """Order-arrival decay vs distance from mid."""
    A: float | None = None
    """Arrival intensity scale; if None, derived from ``dt`` and ``M``."""
    T: float = 1.0
    """Session horizon (limited-horizon mode)."""
    q_max: float = 10.0
    """Inventory bound used by unlimited-horizon quotes."""
    M: float | None = None
    """Half-spread proxy for default ``A`` (defaults to ``s0/200``)."""


@dataclass(frozen=True)
class Quotes:
    """Indifference price and optimal bid/ask."""

    reservation: float
    ask: float
    bid: float
    spread: float
    delta_ask: float
    delta_bid: float


def reservation_spread(gamma: float, k: float) -> float:
    """Optimal reservation half-width * 2: ``(2/γ) log(1 + γ/k)``."""
    if gamma <= 0:
        raise ValueError("gamma must be > 0")
    if k <= 0:
        raise ValueError("k must be > 0")
    return (2.0 / gamma) * math.log(1.0 + gamma / k)


def intensity_scale(dt: float, k: float, m: float) -> float:
    """Default arrival scale ``A = 1/(dt · exp(k·M/2))`` from the reference sim."""
    if dt <= 0:
        raise ValueError("dt must be > 0")
    return 1.0 / (dt * math.exp(k * m / 2.0))


def limited_horizon_quotes(
    mid: float,
    inventory: float,
    t: float,
    params: ASParams,
) -> Quotes:
    """Finite-horizon reservation price and symmetric optimal quotes.

    ``r = s − q γ σ² (T − t)``, ``spread = (2/γ) log(1+γ/k)``.
    """
    remaining = max(params.T - t, 0.0)
    r = mid - inventory * params.gamma * (params.sigma**2) * remaining
    spread = reservation_spread(params.gamma, params.k)
    ask = r + spread / 2.0
    bid = r - spread / 2.0
    return Quotes(
        reservation=r,
        ask=ask,
        bid=bid,
        spread=spread,
        delta_ask=ask - mid,
        delta_bid=mid - bid,
    )


def unlimited_horizon_quotes(
    mid: float,
    inventory: float,
    params: ASParams,
) -> Quotes:
    """Stationary (infinite-horizon) AS quotes with inventory bound ``q_max``."""
    gamma = params.gamma
    sigma = params.sigma
    q_max = params.q_max
    w = 0.5 * (gamma**2) * (sigma**2) * (q_max + 1.0) ** 2
    denom = 2.0 * w - (gamma**2) * (inventory**2) * (sigma**2)
    if denom <= 0:
        raise ValueError("inventory too large for unlimited-horizon bound")
    coef = (gamma**2) * (sigma**2) / denom
    ask = mid + math.log(1.0 + (1.0 - 2.0 * inventory) * coef) / gamma
    bid = mid + math.log(1.0 + (-1.0 - 2.0 * inventory) * coef) / gamma
    r = (ask + bid) / 2.0
    return Quotes(
        reservation=r,
        ask=ask,
        bid=bid,
        spread=ask - bid,
        delta_ask=ask - mid,
        delta_bid=mid - bid,
    )


def arrival_intensity(A: float, k: float, delta: float) -> float:
    """Poisson intensity ``λ = A exp(−k δ)`` for a quote at distance ``δ``."""
    return A * math.exp(-k * delta)


def fill_probability(intensity: float, dt: float) -> float:
    """Probability of at least one fill in ``dt``: ``1 − exp(−λ dt)``."""
    if dt < 0:
        raise ValueError("dt must be >= 0")
    return 1.0 - math.exp(-intensity * dt)
