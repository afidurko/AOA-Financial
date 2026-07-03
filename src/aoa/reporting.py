"""Reporting: turn the journal + a live broker snapshot into a readable summary.

The journal is an append-only record of every cycle and order, so it gives an
honest picture of *activity* (what the swarm proposed, blocked, and submitted).
True realized P&L requires fill data the journal doesn't capture, so the live
snapshot supplies **unrealized** P&L (from open positions) and the **day's P&L**
versus the persisted daily baseline. The two together are the report.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from aoa.brokerage.models import Position


@dataclass
class JournalSummary:
    cycles: int = 0
    candidates_total: int = 0
    orders_submitted: int = 0
    orders_by_side: dict[str, int] = field(default_factory=dict)
    dry_runs: int = 0
    errors: int = 0
    reentry_skips: int = 0
    blocked: list[tuple[str, str]] = field(default_factory=list)
    first_ts: str | None = None
    last_ts: str | None = None
    last_logged_equity: float | None = None

    @property
    def blocked_reason_counts(self) -> dict[str, int]:
        return dict(Counter(reason for _, reason in self.blocked))


def summarize_journal(entries: list[dict]) -> JournalSummary:
    s = JournalSummary()
    side_counts: Counter[str] = Counter()
    for e in entries:
        event = e.get("event")
        ts = e.get("ts")
        if ts:
            if s.first_ts is None:
                s.first_ts = ts
            s.last_ts = ts
        if event == "cycle.start":
            s.cycles += 1
            if e.get("equity") is not None:
                s.last_logged_equity = e.get("equity")
        elif event == "scanner.candidates":
            s.candidates_total += len(e.get("candidates", []) or [])
        elif event == "order.submitted":
            s.orders_submitted += 1
            side_counts[e.get("side", "?")] += 1
        elif event == "order.dry_run":
            s.dry_runs += 1
        elif event == "order.error":
            s.errors += 1
        elif event == "proposal.skipped":
            s.reentry_skips += 1
        elif event == "risk.review":
            for p in e.get("proposals", []) or []:
                if not p.get("approved"):
                    notes = p.get("risk_notes") or []
                    s.blocked.append((p.get("symbol", "?"), notes[-1] if notes else "blocked"))
    s.orders_by_side = dict(side_counts)
    return s


@dataclass
class PositionPnL:
    n: int = 0
    market_value: float = 0.0
    unrealized_pl: float = 0.0
    winners: int = 0
    losers: int = 0
    best: tuple[str, float] | None = None
    worst: tuple[str, float] | None = None


def position_pnl(positions: list[Position]) -> PositionPnL:
    p = PositionPnL(n=len(positions))
    p.market_value = round(sum(pos.market_value for pos in positions), 2)
    p.unrealized_pl = round(sum(pos.unrealized_pl for pos in positions), 2)
    p.winners = sum(1 for pos in positions if pos.unrealized_pl > 0)
    p.losers = sum(1 for pos in positions if pos.unrealized_pl < 0)
    if positions:
        best = max(positions, key=lambda x: x.unrealized_pl)
        worst = min(positions, key=lambda x: x.unrealized_pl)
        p.best = (best.symbol, round(best.unrealized_pl, 2))
        p.worst = (worst.symbol, round(worst.unrealized_pl, 2))
    return p
