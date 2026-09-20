"""``aoa analytics`` — terminal views over the decision analytics store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aoa.analytics.insights import (
    agent_scorecard,
    analytics_summary,
    proposal_funnel,
    stage_latency,
)
from aoa.analytics.store import AnalyticsStore

VIEWS = ("summary", "agents", "stages", "funnel")


def run_analytics_view(
    db_path: str | Path, view: str, *, limit_runs: int = 200, as_json: bool = False
) -> int:
    path = Path(db_path)
    if not path.exists():
        print(f"No analytics database at {path}. Run a cycle first: aoa run")
        return 1
    with AnalyticsStore(path) as store:
        if view == "agents":
            data: Any = agent_scorecard(store, limit_runs=limit_runs)
        elif view == "stages":
            data = stage_latency(store, limit_runs=limit_runs)
        elif view == "funnel":
            data = proposal_funnel(store, limit_runs=limit_runs)
        else:
            data = analytics_summary(store, limit_runs=limit_runs)
    if as_json:
        print(json.dumps(data, indent=2))
        return 0
    print(f"=== Analytics ({view}) — last {limit_runs} runs · {path} ===")
    if view == "agents":
        print(format_agents(data))
    elif view == "stages":
        print(format_stages(data))
    elif view == "funnel":
        print(format_funnel(data))
    else:
        print(format_throughput(data["throughput"]))
        print("\n--- Agents ---")
        print(format_agents(data["agents"]))
        print("\n--- Stages ---")
        print(format_stages(data["stages"]))
        print("\n--- Proposal funnel ---")
        print(format_funnel(data["funnel"]))
    return 0


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "(no data)"
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    out = [line, "  ".join("-" * w for w in widths)]
    for r in rows:
        out.append("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)))
    return "\n".join(out)


def format_throughput(tp: dict[str, Any]) -> str:
    if not tp.get("cycles"):
        return "No cycles recorded yet."
    return (
        f"Cycles: {tp['cycles']} ({tp['first']} → {tp['last']}) · "
        f"{tp['cycles_per_day']}/day · halt rate {_pct(tp['halt_rate'])}\n"
        f"Wall time: avg {tp['avg_wall_ms'] / 1000:.1f}s · p95 {tp['p95_wall_ms'] / 1000:.1f}s"
    )


def format_agents(rows: list[dict[str, Any]]) -> str:
    return _table(
        ["agent", "signals", "tickers", "avg conv", "long/short/neutral", "scored", "hit", "avg signed ret"],
        [
            [
                r["agent"],
                str(r["signals"]),
                str(r["tickers"]),
                "—" if r["avg_conviction"] is None else f"{r['avg_conviction']:.2f}",
                f"{r['long']}/{r['short']}/{r['neutral']}",
                str(r["scored"]),
                _pct(r["hit_rate"]),
                "—" if r["avg_signed_return_pct"] is None else f"{r['avg_signed_return_pct']:+.2f}%",
            ]
            for r in rows
        ],
    )


def format_stages(rows: list[dict[str, Any]]) -> str:
    return _table(
        ["stage", "runs", "skipped", "avg ms", "p50 ms", "p95 ms", "max ms"],
        [
            [
                r["stage"],
                str(r["runs"]),
                str(r["skipped"]),
                f"{r['avg_ms']:.0f}",
                f"{r['p50_ms']:.0f}",
                f"{r['p95_ms']:.0f}",
                f"{r['max_ms']:.0f}",
            ]
            for r in rows
        ],
    )


def format_funnel(f: dict[str, Any]) -> str:
    head = (
        f"Proposals {f['proposals']} → approved {f['approved']} "
        f"({_pct(f['approval_rate'])}) · approved notional ${f['approved_notional']:,.0f}"
    )
    side = _table(
        ["side", "proposals", "approved", "rate"],
        [[g["side"], str(g["proposals"]), str(g["approved"]), _pct(g["approval_rate"])]
         for g in f["by_side"]],
    )
    strat = _table(
        ["strategy", "proposals", "approved", "rate"],
        [[g["strategy"], str(g["proposals"]), str(g["approved"]), _pct(g["approval_rate"])]
         for g in f["by_strategy"]],
    )
    return f"{head}\n\n{side}\n\n{strat}"
