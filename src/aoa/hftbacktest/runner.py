"""Offline runners for the optional hftbacktest engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from aoa.hftbacktest.synthetic import make_synthetic_l2_tape


@dataclass(frozen=True)
class SmokeResult:
    """Summary of a synthetic L2 smoke backtest."""

    ok: bool
    steps: int
    best_bid: float | None
    best_ask: float | None
    position: float
    mid: float
    tick_size: float
    lot_size: float
    n_events: int
    seed: int
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_npz_smoke(
    *,
    n_events: int = 400,
    mid: float = 100.0,
    tick_size: float = 0.01,
    lot_size: float = 0.001,
    steps: int = 20,
    step_ns: int = 50_000_000,
    seed: int = 1,
) -> SmokeResult:
    """Run a short HashMapMarketDepth backtest on synthetic depth events.

    Does not place orders — only advances time and reads the book so the
    optional dependency and Numba engine are proven wired correctly.
    """
    try:
        from hftbacktest import BacktestAsset, HashMapMarketDepthBacktest
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            'hftbacktest is not installed. Run: pip install -e ".[hftbacktest]"'
        ) from exc

    snap, feed = make_synthetic_l2_tape(
        n_events=n_events,
        mid=mid,
        tick_size=tick_size,
        lot_size=lot_size,
        seed=seed,
    )

    asset = (
        BacktestAsset()
        .data([feed])
        .initial_snapshot(snap)
        .linear_asset(1.0)
        .constant_order_latency(10_000, 10_000)
        .risk_adverse_queue_model()
        .no_partial_fill_exchange()
        .trading_value_fee_model(-0.0001, 0.0005)
        .tick_size(tick_size)
        .lot_size(lot_size)
        .last_trades_capacity(0)
    )

    hbt = HashMapMarketDepthBacktest([asset])
    try:
        advanced = 0
        for _ in range(steps):
            if hbt.elapse(step_ns) != 0:
                break
            advanced += 1
        depth = hbt.depth(0)
        best_bid = float(depth.best_bid)
        best_ask = float(depth.best_ask)
        position = float(hbt.position(0))
    finally:
        hbt.close()

    ok = advanced > 0 and best_bid > 0 and best_ask > best_bid
    return SmokeResult(
        ok=ok,
        steps=advanced,
        best_bid=best_bid,
        best_ask=best_ask,
        position=position,
        mid=mid,
        tick_size=tick_size,
        lot_size=lot_size,
        n_events=n_events,
        seed=seed,
        detail="synthetic L2 depth replay (no orders)" if ok else "engine failed to advance",
    )


def load_npz_from_npz(
    data_path: str,
    *,
    tick_size: float,
    lot_size: float,
    latency_ns: int = 10_000,
) -> Any:
    """Build a ``HashMapMarketDepthBacktest`` from an on-disk NPZ/feed path.

    ``data_path`` is passed to ``BacktestAsset.data`` / ``add_file`` as supported
    by the installed hftbacktest version. Caller owns ``close()``.
    """
    from hftbacktest import BacktestAsset, HashMapMarketDepthBacktest

    asset = (
        BacktestAsset()
        .data([data_path])
        .linear_asset(1.0)
        .constant_order_latency(latency_ns, latency_ns)
        .risk_adverse_queue_model()
        .no_partial_fill_exchange()
        .trading_value_fee_model(-0.0001, 0.0005)
        .tick_size(tick_size)
        .lot_size(lot_size)
        .last_trades_capacity(0)
    )
    return HashMapMarketDepthBacktest([asset])
