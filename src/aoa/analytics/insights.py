"""Decision analytics over the cycle history in :class:`AnalyticsStore`.

Four read-only views, each a plain function returning JSON-ready dicts:

- :func:`agent_scorecard` — per agent: volume, conviction, direction mix, and
  the hit rate of its directional calls against the next cycle's price.
- :func:`stage_latency` — per pipeline stage: p50 / p95 / max duration, so a
  slow lane is visible before it becomes a missed entry.
- :func:`proposal_funnel` — proposals → approvals by side and strategy.
- :func:`cycle_throughput` — cycles per day, wall time, halt rate.

:func:`analytics_summary` bundles all four for the CLI, API and dashboard.
Everything runs in a few indexed SQL statements plus linear Python; no pandas.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime
from typing import Any

from aoa.analytics.store import AnalyticsStore

# Directional vocabulary across agents. Anything else (Julie's validated/review,
# Morgan's volume regime, Cindy's letter grades) is descriptive and not scored.
_LONG = frozenset({"bullish", "up", "long", "consider_long", "buy"})
_SHORT = frozenset({"bearish", "down", "short", "consider_short_exit", "sell"})


def direction_sign(direction: object) -> int:
    d = str(direction or "").strip().lower()
    if d in _LONG:
        return 1
    if d in _SHORT:
        return -1
    return 0


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, round(q * (len(sorted_values) - 1))))
    return sorted_values[idx]


def _run_order(store: AnalyticsStore, limit_runs: int) -> dict[str, int]:
    """Map run_id → chronological index over the most recent ``limit_runs``."""
    rows = store.rows(
        "SELECT run_id FROM cycle_runs ORDER BY started_at DESC LIMIT ?", (limit_runs,)
    )
    return {r["run_id"]: i for i, r in enumerate(reversed(rows))}


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def agent_scorecard(store: AnalyticsStore, *, limit_runs: int = 200) -> list[dict[str, Any]]:
    """Per-agent signal stats plus next-cycle hit rate for directional calls."""
    order = _run_order(store, limit_runs)
    if not order:
        return []
    run_ids = list(order)
    ph = _placeholders(len(run_ids))
    signals = store.rows(
        f"SELECT run_id, ticker, agent, direction, conviction FROM cycle_signals "
        f"WHERE run_id IN ({ph})",
        run_ids,
    )
    prices = store.rows(
        f"SELECT run_id, ticker, price FROM cycle_prices WHERE run_id IN ({ph})", run_ids
    )

    # ticker → (sorted run indices, prices aligned to those indices)
    by_ticker: dict[str, tuple[list[int], list[float]]] = {}
    tmp: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for p in prices:
        tmp[p["ticker"]].append((order[p["run_id"]], p["price"]))
    for ticker, pairs in tmp.items():
        pairs.sort()
        by_ticker[ticker] = ([i for i, _ in pairs], [px for _, px in pairs])

    stats: dict[str, dict[str, Any]] = {}
    for s in signals:
        agent = s["agent"] or "unknown"
        st = stats.setdefault(
            agent,
            {
                "agent": agent,
                "signals": 0,
                "tickers": set(),
                "conviction_sum": 0.0,
                "conviction_n": 0,
                "long": 0,
                "short": 0,
                "neutral": 0,
                "scored": 0,
                "hits": 0,
                "realized_sum": 0.0,
            },
        )
        st["signals"] += 1
        st["tickers"].add(s["ticker"])
        conv = s["conviction"]
        if isinstance(conv, (int, float)):
            st["conviction_sum"] += float(conv)
            st["conviction_n"] += 1
        sign = direction_sign(s["direction"])
        st["long" if sign > 0 else "short" if sign < 0 else "neutral"] += 1
        if sign == 0:
            continue
        series = by_ticker.get(s["ticker"])
        if not series:
            continue
        idxs, pxs = series
        i = order[s["run_id"]]
        at = bisect_right(idxs, i) - 1
        if at < 0 or idxs[at] != i or at + 1 >= len(idxs):
            continue  # no price this run, or no later run to score against
        realized = pxs[at + 1] / pxs[at] - 1.0
        st["scored"] += 1
        st["realized_sum"] += sign * realized
        if realized * sign > 0:
            st["hits"] += 1

    out = []
    for st in stats.values():
        scored = st["scored"]
        out.append(
            {
                "agent": st["agent"],
                "signals": st["signals"],
                "tickers": len(st["tickers"]),
                "avg_conviction": (
                    round(st["conviction_sum"] / st["conviction_n"], 3)
                    if st["conviction_n"]
                    else None
                ),
                "long": st["long"],
                "short": st["short"],
                "neutral": st["neutral"],
                "scored": scored,
                "hit_rate": round(st["hits"] / scored, 3) if scored else None,
                "avg_signed_return_pct": (
                    round(100 * st["realized_sum"] / scored, 3) if scored else None
                ),
            }
        )
    out.sort(key=lambda r: (-r["signals"], r["agent"]))
    return out


def stage_latency(store: AnalyticsStore, *, limit_runs: int = 200) -> list[dict[str, Any]]:
    """Per-stage duration distribution across recent runs."""
    order = _run_order(store, limit_runs)
    if not order:
        return []
    run_ids = list(order)
    rows = store.rows(
        f"SELECT stage, duration_ms, skipped FROM stage_metrics "
        f"WHERE run_id IN ({_placeholders(len(run_ids))})",
        run_ids,
    )
    durations: dict[str, list[float]] = defaultdict(list)
    skipped: dict[str, int] = defaultdict(int)
    for r in rows:
        if r["skipped"]:
            skipped[r["stage"]] += 1
        else:
            durations[r["stage"]].append(float(r["duration_ms"]))
    out = []
    for stage in sorted(set(durations) | set(skipped)):
        vals = sorted(durations.get(stage, []))
        out.append(
            {
                "stage": stage,
                "runs": len(vals),
                "skipped": skipped.get(stage, 0),
                "avg_ms": round(sum(vals) / len(vals), 1) if vals else 0.0,
                "p50_ms": round(_percentile(vals, 0.5), 1),
                "p95_ms": round(_percentile(vals, 0.95), 1),
                "max_ms": round(vals[-1], 1) if vals else 0.0,
            }
        )
    out.sort(key=lambda r: -r["avg_ms"])
    return out


def proposal_funnel(store: AnalyticsStore, *, limit_runs: int = 200) -> dict[str, Any]:
    """Proposal → approval funnel by side and strategy, with approved notional."""
    order = _run_order(store, limit_runs)
    if not order:
        return {"proposals": 0, "approved": 0, "approval_rate": 0.0, "approved_notional": 0.0,
                "by_side": [], "by_strategy": []}
    run_ids = list(order)
    ph = _placeholders(len(run_ids))
    rows = store.rows(
        f"SELECT side, strategy, approved, est_notional FROM cycle_proposals "
        f"WHERE run_id IN ({ph})",
        run_ids,
    )
    total = len(rows)
    approved = sum(1 for r in rows if r["approved"])
    notional = sum(float(r["est_notional"] or 0) for r in rows if r["approved"])

    def _group(key: str) -> list[dict[str, Any]]:
        agg: dict[str, dict[str, Any]] = {}
        for r in rows:
            k = str(r[key] or "unknown")
            g = agg.setdefault(k, {key: k, "proposals": 0, "approved": 0})
            g["proposals"] += 1
            g["approved"] += 1 if r["approved"] else 0
        for g in agg.values():
            g["approval_rate"] = round(g["approved"] / g["proposals"], 3)
        return sorted(agg.values(), key=lambda g: (-g["proposals"], g[key]))

    return {
        "proposals": total,
        "approved": approved,
        "approval_rate": round(approved / total, 3) if total else 0.0,
        "approved_notional": round(notional, 2),
        "by_side": _group("side"),
        "by_strategy": _group("strategy"),
    }


def cycle_throughput(store: AnalyticsStore, *, limit_runs: int = 200) -> dict[str, Any]:
    """Cycle count, wall time, halt rate, and cycles/day over recent runs."""
    rows = store.rows(
        "SELECT started_at, completed_at, halted FROM cycle_runs "
        "ORDER BY started_at DESC LIMIT ?",
        (limit_runs,),
    )
    if not rows:
        return {"cycles": 0, "halted": 0, "halt_rate": 0.0, "avg_wall_ms": 0.0,
                "p95_wall_ms": 0.0, "cycles_per_day": 0.0, "first": None, "last": None}
    walls: list[float] = []
    stamps: list[datetime] = []
    for r in rows:
        try:
            s = datetime.fromisoformat(r["started_at"])
            e = datetime.fromisoformat(r["completed_at"])
        except (TypeError, ValueError):
            continue
        stamps.append(s)
        walls.append(max(0.0, (e - s).total_seconds() * 1000))
    walls.sort()
    halted = sum(1 for r in rows if r["halted"])
    span_days = 0.0
    if len(stamps) >= 2:
        span_days = (max(stamps) - min(stamps)).total_seconds() / 86400
    return {
        "cycles": len(rows),
        "halted": halted,
        "halt_rate": round(halted / len(rows), 3),
        "avg_wall_ms": round(sum(walls) / len(walls), 1) if walls else 0.0,
        "p95_wall_ms": round(_percentile(walls, 0.95), 1),
        "cycles_per_day": round(len(rows) / span_days, 2) if span_days > 0 else float(len(rows)),
        "first": rows[-1]["started_at"],
        "last": rows[0]["started_at"],
    }


def analytics_summary(store: AnalyticsStore, *, limit_runs: int = 200) -> dict[str, Any]:
    return {
        "throughput": cycle_throughput(store, limit_runs=limit_runs),
        "agents": agent_scorecard(store, limit_runs=limit_runs),
        "stages": stage_latency(store, limit_runs=limit_runs),
        "funnel": proposal_funnel(store, limit_runs=limit_runs),
    }
