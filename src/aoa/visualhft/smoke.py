"""Synthetic smoke runner for VisualHFT study ports (offline, no live data)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from aoa.visualhft.studies import TradePrint, VPINState, lob_imbalance, order_to_trade_ratio

# Keep smoke tape large enough to complete ≥1 VPIN bucket (bucket_volume=20).
_MIN_SMOKE_TRADES = 20
_VPIN_BUCKET = 20.0
_VPIN_WINDOW = 10


@dataclass(frozen=True)
class SmokeResult:
    """Outcome of ``run_synthetic_smoke``."""

    ok: bool
    lob_imbalance: float
    vpin: float
    order_to_trade_ratio: float
    mid_price: float
    n_trades: int
    seed: int
    vpin_buckets: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_synthetic_smoke(*, n_trades: int = 200, seed: int = 1) -> SmokeResult:
    """Exercise ported studies on a deterministic synthetic L2 + trade tape.

    Never contacts venues or brokers. Suitable for ``aoa visualhft smoke``.
    """
    if n_trades < _MIN_SMOKE_TRADES:
        raise ValueError(f"n_trades must be >= {_MIN_SMOKE_TRADES} (got {n_trades})")

    # Deterministic LCG — no numpy dependency.
    state = (seed * 1103515245 + 12345) & 0x7FFFFFFF

    def _rand() -> float:
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    mid = 100.0
    tick = 0.01
    levels = 5
    bid_sizes = [10.0 + 5.0 * _rand() for _ in range(levels)]
    ask_sizes = [10.0 + 5.0 * _rand() for _ in range(levels)]
    # Skew bids heavier so imbalance is detectably positive for smoke asserts.
    bid_sizes[0] += 25.0

    imb = lob_imbalance(bid_sizes, ask_sizes, book_depth=levels)

    vpin_state = VPINState(
        bucket_volume=_VPIN_BUCKET, n_buckets=_VPIN_WINDOW, mid_price=mid
    )
    for i in range(n_trades):
        # Mild buy pressure so VPIN buckets complete with imbalance > 0.
        buy = _rand() < 0.62
        px = mid + (tick if buy else -tick) * (1 + int(3 * _rand()))
        size = 1.0 + 4.0 * _rand()
        vpin_state.on_trade(TradePrint(price=px, size=size, is_buy=buy))
        if i % 40 == 0:
            mid = round(mid + tick * (1 if _rand() < 0.55 else -1), 2)
            vpin_state.set_mid(mid)

    mid = round(mid, 2)

    # Synthetic L2 counter deltas + trades for OTR.
    added, deleted, updated, trades = 80, 40, 15, max(1, n_trades // 10)
    otr = order_to_trade_ratio(
        added_delta=added,
        deleted_delta=deleted,
        updated_delta=updated,
        trade_count=trades,
    )

    ok = (
        -1.0 <= imb <= 1.0
        and imb > 0.0
        and vpin_state.completed_buckets >= 1
        and 0.0 <= vpin_state.value <= 1.0
        and otr > -1.0
    )
    return SmokeResult(
        ok=ok,
        lob_imbalance=imb,
        vpin=vpin_state.value,
        order_to_trade_ratio=otr,
        mid_price=mid,
        n_trades=n_trades,
        seed=seed,
        vpin_buckets=vpin_state.completed_buckets,
    )
