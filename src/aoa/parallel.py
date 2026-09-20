"""One fan-out primitive for every agent, sub-agent, and data lane.

The swarm used to carry six hand-rolled ``ThreadPoolExecutor`` blocks, each
re-implementing "run these independent calls, then put the results back in
order". ``fan_out`` is that pattern once: results are returned in the same
order as ``items`` (so no post-hoc sorting), the pool is skipped entirely when
it cannot help, and every worker is bounded by ``workers``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


def fan_out(
    fn: Callable[[T], R],
    items: Iterable[T],
    *,
    workers: int = 4,
    parallel: bool = True,
) -> list[R]:
    """Apply ``fn`` to each item, concurrently when it pays off.

    Order of results always matches order of ``items``. Runs inline (no thread
    pool) when ``parallel`` is False, ``workers`` <= 1, or there is at most one
    item — the common small-cycle case where pool start-up would only add
    latency. Exceptions propagate exactly as they would from a plain loop.
    """
    seq: Sequence[T] = items if isinstance(items, Sequence) else list(items)
    if not seq:
        return []
    width = min(int(workers), len(seq))
    if not parallel or width <= 1:
        return [fn(item) for item in seq]
    with ThreadPoolExecutor(max_workers=width) as pool:
        return list(pool.map(fn, seq))


def fan_out_named(
    lanes: dict[str, Callable[[], R]],
    *,
    workers: int = 4,
    parallel: bool = True,
) -> dict[str, R]:
    """Run independent zero-arg lanes and return ``{name: result}``.

    Used for heterogeneous work (e.g. several team members analysing the same
    snapshots) where each lane is a different callable rather than one callable
    over many items.
    """
    names = list(lanes)
    results = fan_out(lambda name: lanes[name](), names, workers=workers, parallel=parallel)
    return dict(zip(names, results, strict=True))
