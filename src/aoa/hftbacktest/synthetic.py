"""Synthetic L2 event tapes for offline smoke tests (no external tick files)."""

from __future__ import annotations

from typing import Any


def make_synthetic_l2_tape(
    *,
    n_events: int = 400,
    mid: float = 100.0,
    tick_size: float = 0.01,
    lot_size: float = 0.001,
    start_ts_ns: int = 1_000_000_000,
    step_ns: int = 10_000_000,
    seed: int = 1,
) -> tuple[Any, Any]:
    """Build ``(initial_snapshot, feed_events)`` arrays with ``event_dtype``.

    Produces alternating bid/ask depth updates oscillating around ``mid``.
    Suitable for verifying the engine wiring — not for research-grade edges.
    """
    import numpy as np
    from hftbacktest import (
        BUY_EVENT,
        DEPTH_EVENT,
        EXCH_EVENT,
        LOCAL_EVENT,
        SELL_EVENT,
        event_dtype,
    )

    if n_events < 4:
        raise ValueError("n_events must be at least 4")
    if tick_size <= 0 or lot_size <= 0:
        raise ValueError("tick_size and lot_size must be positive")

    rng = np.random.default_rng(seed)

    snap = np.zeros(2, dtype=event_dtype)
    bid0 = np.floor(mid / tick_size) * tick_size - tick_size
    ask0 = bid0 + tick_size
    snap[0]["ev"] = DEPTH_EVENT | BUY_EVENT | LOCAL_EVENT | EXCH_EVENT
    snap[0]["exch_ts"] = start_ts_ns - 1
    snap[0]["local_ts"] = start_ts_ns - 1
    snap[0]["px"] = float(bid0)
    snap[0]["qty"] = 100.0
    snap[1]["ev"] = DEPTH_EVENT | SELL_EVENT | LOCAL_EVENT | EXCH_EVENT
    snap[1]["exch_ts"] = start_ts_ns - 1
    snap[1]["local_ts"] = start_ts_ns - 1
    snap[1]["px"] = float(ask0)
    snap[1]["qty"] = 100.0

    feed = np.zeros(n_events, dtype=event_dtype)
    for i in range(n_events):
        ts = start_ts_ns + i * step_ns
        wobble = 0.05 * np.sin(i / 20.0) + float(rng.normal(0.0, 0.005))
        m = mid + wobble
        bid = np.floor(m / tick_size) * tick_size - tick_size
        ask = bid + tick_size
        qty = float(max(lot_size, 1.0 + abs(rng.normal(0.0, 0.5))))
        if i % 2 == 0:
            feed[i]["ev"] = DEPTH_EVENT | BUY_EVENT | LOCAL_EVENT | EXCH_EVENT
            feed[i]["px"] = float(bid)
        else:
            feed[i]["ev"] = DEPTH_EVENT | SELL_EVENT | LOCAL_EVENT | EXCH_EVENT
            feed[i]["px"] = float(ask)
        feed[i]["exch_ts"] = ts
        feed[i]["local_ts"] = ts + 100_000
        feed[i]["qty"] = qty

    return snap, feed
