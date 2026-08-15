"""Pure-Python ports of VisualHFT microstructure study formulas.

Formulas match the open-source VisualHFT plugins (Apache-2.0). These helpers
operate on plain Python sequences — no .NET runtime, no live brokerage.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


def lob_imbalance(
    bid_sizes: Sequence[float],
    ask_sizes: Sequence[float],
    *,
    book_depth: int | None = None,
) -> float:
    """Limit-order-book size imbalance in ``[-1, 1]``.

    Mirrors ``OrderFlowAnalysis.Calculate_OrderImbalance``::

        (Σ bid_i - Σ ask_i) / (Σ bid_i + Σ ask_i)

    over the first ``book_depth`` levels (default: all provided levels).
    Returns ``0.0`` when either side is empty or total size is zero.
    """
    if not bid_sizes or not ask_sizes:
        return 0.0
    depth = book_depth if book_depth is not None else max(len(bid_sizes), len(ask_sizes))
    if depth <= 0:
        return 0.0
    total_bid = sum(float(bid_sizes[i]) for i in range(min(depth, len(bid_sizes))))
    total_ask = sum(float(ask_sizes[i]) for i in range(min(depth, len(ask_sizes))))
    denom = total_bid + total_ask
    if denom == 0:
        return 0.0
    return (total_bid - total_ask) / denom


def order_to_trade_ratio(
    *,
    added_delta: int,
    deleted_delta: int,
    updated_delta: int,
    trade_count: int,
    floor: int = 1,
) -> float:
    """L2 order-to-trade ratio from VisualHFT ``OrderToTradeRatioStudy``.

    ``OTR = (addedΔ + deletedΔ + 2×updatedΔ) / max(trades, floor) - 1``
    """
    order_events = int(added_delta) + int(deleted_delta) + 2 * int(updated_delta)
    denom = max(int(trade_count), int(floor))
    if denom == 0:
        return 0.0
    return order_events / denom - 1.0


@dataclass
class TradePrint:
    """One public trade for VPIN classification."""

    price: float
    size: float
    is_buy: bool | None = None


@dataclass
class VPINState:
    """Rolling VPIN bucket state (volume-synchronized).

    Matches ``VPINStudy``: classify vs mid (price ≥ mid → buy), fill fixed-size
    volume buckets, and average ``|V_buy - V_sell| / V_bucket`` over a rolling
    window of completed buckets.
    """

    bucket_volume: float = 50.0
    n_buckets: int = 50
    mid_price: float = 0.0
    current_buy: float = 0.0
    current_sell: float = 0.0
    current_volume: float = 0.0
    imbalances: list[float] = field(default_factory=list)
    _index: int = 0
    _count: int = 0
    _rolling_sum: float = 0.0

    def __post_init__(self) -> None:
        if self.bucket_volume <= 0:
            raise ValueError("bucket_volume must be > 0")
        if self.n_buckets <= 0:
            raise ValueError("n_buckets must be > 0")
        if not self.imbalances:
            self.imbalances = [0.0] * self.n_buckets
        elif len(self.imbalances) != self.n_buckets:
            raise ValueError("imbalances length must equal n_buckets")

    @property
    def value(self) -> float:
        if self._count <= 0:
            return 0.0
        return self._rolling_sum / self._count

    def set_mid(self, mid: float) -> float:
        self.mid_price = float(mid)
        return self.value

    def on_trade(self, trade: TradePrint) -> float:
        """Ingest one trade; return current VPIN (interim or after bucket close)."""
        is_buy = trade.is_buy
        if self.mid_price > 0:
            is_buy = trade.price >= self.mid_price
        if is_buy is None:
            return self.value

        remaining = float(trade.size)
        if remaining <= 0:
            return self.value

        if is_buy:
            self.current_buy += remaining
        else:
            self.current_sell += remaining
        self.current_volume += remaining

        while self.current_volume >= self.bucket_volume:
            overflow = self.current_volume - self.bucket_volume
            if is_buy:
                self.current_buy -= overflow
            else:
                self.current_sell -= overflow
            self.current_volume = self.bucket_volume
            self._complete_bucket()
            self.current_buy = overflow if is_buy else 0.0
            self.current_sell = 0.0 if is_buy else overflow
            self.current_volume = overflow

        return self.value

    def _complete_bucket(self) -> None:
        imbalance = abs(self.current_buy - self.current_sell) / self.bucket_volume
        if self._count == self.n_buckets:
            self._rolling_sum -= self.imbalances[self._index]
        else:
            self._count += 1
        self.imbalances[self._index] = imbalance
        self._rolling_sum += imbalance
        self._index = (self._index + 1) % self.n_buckets


def vpin_from_trades(
    trades: Iterable[TradePrint],
    *,
    mid_price: float,
    bucket_volume: float = 50.0,
    n_buckets: int = 50,
) -> float:
    """Convenience: run a trade sequence through :class:`VPINState`."""
    state = VPINState(bucket_volume=bucket_volume, n_buckets=n_buckets, mid_price=mid_price)
    value = 0.0
    for trade in trades:
        value = state.on_trade(trade)
    return value
