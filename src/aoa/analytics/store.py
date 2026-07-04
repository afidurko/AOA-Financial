"""SQLite analytics store for live swarm cycles, notifications, and approvals."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class AnalyticsStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA_PATH.read_text())
        self._conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> AnalyticsStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def record_cycle(
        self,
        *,
        run_id: str,
        started_at: str,
        completed_at: str,
        mode: str,
        halted: bool,
        halt_reason: str,
        payload: dict[str, Any],
    ) -> None:
        with self.transaction() as c:
            c.execute(
                """INSERT INTO cycle_runs(run_id,started_at,completed_at,mode,halted,
                       halt_reason,cycles_total,payload)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(run_id) DO UPDATE SET
                     completed_at=excluded.completed_at,
                     halted=excluded.halted,
                     halt_reason=excluded.halt_reason,
                     payload=excluded.payload""",
                (
                    run_id,
                    started_at,
                    completed_at,
                    mode,
                    1 if halted else 0,
                    halt_reason or None,
                    1,
                    json.dumps(payload),
                ),
            )

    def insert_signals(self, run_id: str, signals: list[dict[str, Any]]) -> None:
        with self.transaction() as c:
            for sig in signals:
                c.execute(
                    """INSERT INTO cycle_signals(run_id,ticker,agent,direction,conviction,
                           summary,metrics)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(run_id,ticker,agent) DO UPDATE SET
                         direction=excluded.direction,
                         conviction=excluded.conviction,
                         summary=excluded.summary,
                         metrics=excluded.metrics""",
                    (
                        run_id,
                        sig.get("ticker") or sig.get("symbol", ""),
                        sig.get("agent") or sig.get("analyst", ""),
                        sig.get("direction", ""),
                        sig.get("conviction") or sig.get("score"),
                        sig.get("summary", ""),
                        json.dumps(sig.get("metrics") or {}),
                    ),
                )

    def insert_proposals(self, run_id: str, proposals: list[dict[str, Any]]) -> None:
        with self.transaction() as c:
            for p in proposals:
                c.execute(
                    """INSERT INTO cycle_proposals(run_id,ticker,side,qty,approved,strategy,
                           est_notional,rationale,payload)
                       VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(run_id,ticker,side) DO UPDATE SET
                         qty=excluded.qty,
                         approved=excluded.approved,
                         strategy=excluded.strategy,
                         est_notional=excluded.est_notional,
                         rationale=excluded.rationale,
                         payload=excluded.payload""",
                    (
                        run_id,
                        p.get("symbol", ""),
                        p.get("side", ""),
                        p.get("qty"),
                        1 if p.get("approved") else 0,
                        p.get("strategy", ""),
                        p.get("est_notional"),
                        p.get("rationale", ""),
                        json.dumps(p),
                    ),
                )

    def insert_stage_metric(
        self, run_id: str, stage: str, duration_ms: float, *, skipped: bool = False
    ) -> None:
        with self.transaction() as c:
            c.execute(
                """INSERT INTO stage_metrics(run_id,stage,duration_ms,skipped)
                   VALUES(?,?,?,?)
                   ON CONFLICT(run_id,stage) DO UPDATE SET
                     duration_ms=excluded.duration_ms,
                     skipped=excluded.skipped""",
                (run_id, stage, duration_ms, 1 if skipped else 0),
            )

    def log_notification(
        self,
        *,
        kind: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
        run_id: str = "",
        pushed: bool = False,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as c:
            cur = c.execute(
                """INSERT INTO notification_log(run_id,kind,title,message,payload,pushed,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    run_id or None,
                    kind,
                    title,
                    message,
                    json.dumps(payload or {}),
                    1 if pushed else 0,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def add_approval(
        self,
        *,
        kind: str,
        title: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        proposal_id: str | None = None,
    ) -> str:
        pid = proposal_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as c:
            c.execute(
                """INSERT INTO approval_inbox(id,kind,title,summary,payload,status,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (pid, kind, title, summary, json.dumps(payload or {}), "pending", now),
            )
        return pid

    def upsert_approval(
        self,
        *,
        kind: str,
        title: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        proposal_id: str | None = None,
    ) -> str:
        pid = proposal_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as c:
            existing = c.execute(
                "SELECT status FROM approval_inbox WHERE id=?",
                (pid,),
            ).fetchone()
            if existing is None:
                c.execute(
                    """INSERT INTO approval_inbox(id,kind,title,summary,payload,status,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (pid, kind, title, summary, json.dumps(payload or {}), "pending", now),
                )
                return pid
            if existing["status"] == "pending":
                c.execute(
                    """UPDATE approval_inbox SET kind=?, title=?, summary=?, payload=?
                       WHERE id=?""",
                    (kind, title, summary, json.dumps(payload or {}), pid),
                )
            return pid

    def resolve_approval(self, approval_id: str, status: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as c:
            cur = c.execute(
                """UPDATE approval_inbox SET status=?, resolved_at=?
                   WHERE id=? AND status='pending'""",
                (status, now, approval_id),
            )
            return cur.rowcount > 0

    def add_research_proposal(
        self,
        *,
        title: str,
        abstract: str,
        source: str,
        source_url: str,
        technique: str,
        backtest_score: float | None = None,
        payload: dict[str, Any] | None = None,
        proposal_id: str | None = None,
    ) -> str:
        pid = proposal_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as c:
            c.execute(
                """INSERT INTO research_proposals(id,title,abstract,source,source_url,
                       technique,backtest_score,status,payload,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid,
                    title,
                    abstract,
                    source,
                    source_url,
                    technique,
                    backtest_score,
                    "pending",
                    json.dumps(payload or {}),
                    now,
                ),
            )
        return pid

    def resolve_research_proposal(self, proposal_id: str, status: str) -> bool:
        with self.transaction() as c:
            cur = c.execute(
                "UPDATE research_proposals SET status=? WHERE id=? AND status='pending'",
                (status, proposal_id),
            )
            return cur.rowcount > 0

    def get_last_cycle(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM cycle_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            out = _row_to_dict(row)
            run_id = out["run_id"]
            out["signals"] = [
                _row_to_dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM cycle_signals WHERE run_id=? ORDER BY ticker, agent",
                    (run_id,),
                )
            ]
            out["proposals"] = [
                _row_to_dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM cycle_proposals WHERE run_id=? ORDER BY ticker",
                    (run_id,),
                )
            ]
            out["stage_metrics"] = [
                _row_to_dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM stage_metrics WHERE run_id=? ORDER BY stage",
                    (run_id,),
                )
            ]
            return out

    def roi_summary(self, limit: int = 30) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT run_id, started_at, halted, payload FROM cycle_runs
                   ORDER BY started_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            total = len(rows)
            halted = sum(1 for r in rows if r["halted"])
            approved = self._conn.execute(
                "SELECT COUNT(*) AS n FROM cycle_proposals WHERE approved=1"
            ).fetchone()
            return {
                "cycles_recorded": total,
                "halt_rate": round(halted / total, 3) if total else 0.0,
                "approved_proposals": approved["n"] if approved else 0,
            }

    def list_approvals(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            q = "SELECT * FROM approval_inbox"
            args: list[Any] = []
            if status:
                q += " WHERE status=?"
                args.append(status)
            q += " ORDER BY created_at DESC LIMIT ?"
            args.append(limit)
            rows = self._conn.execute(q, args).fetchall()
            return [_row_to_dict(r) for r in rows]

    def list_research_proposals(self, *, status: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            q = "SELECT * FROM research_proposals"
            args: list[Any] = []
            if status:
                q += " WHERE status=?"
                args.append(status)
            q += " ORDER BY created_at DESC LIMIT ?"
            args.append(limit)
            return [_row_to_dict(r) for r in self._conn.execute(q, args).fetchall()]

    def upsert_team_expansion(
        self,
        proposal: Any,
        *,
        replace_pending: bool = True,
    ) -> str:
        """Insert or replace a lead's pending team-expansion proposal."""
        now = datetime.now(timezone.utc).isoformat()
        payload = _team_expansion_payload(proposal)
        with self.transaction() as c:
            if replace_pending:
                existing = c.execute(
                    """SELECT id FROM team_expansion_proposals
                       WHERE lead_name=? AND status='pending'""",
                    (proposal.lead_name,),
                ).fetchone()
                if existing is not None:
                    pid = str(existing["id"])
                    c.execute(
                        """UPDATE team_expansion_proposals SET
                           lead_role=?, promotion_title=?, team_name=?, mission=?,
                           payload=?, updated_at=?
                           WHERE id=?""",
                        (
                            proposal.lead_role,
                            proposal.promotion_title,
                            proposal.team_name,
                            proposal.mission,
                            json.dumps(payload),
                            now,
                            pid,
                        ),
                    )
                    return pid

            pid = proposal.proposal_id or str(uuid.uuid4())
            c.execute(
                """INSERT INTO team_expansion_proposals(
                       id, lead_name, lead_role, promotion_title, team_name, mission,
                       status, payload, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid,
                    proposal.lead_name,
                    proposal.lead_role,
                    proposal.promotion_title,
                    proposal.team_name,
                    proposal.mission,
                    proposal.status or "pending",
                    json.dumps(payload),
                    now,
                    now,
                ),
            )
            return pid

    def list_team_expansions(
        self, *, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        with self._lock:
            q = "SELECT * FROM team_expansion_proposals"
            args: list[Any] = []
            if status:
                q += " WHERE status=?"
                args.append(status)
            q += " ORDER BY lead_name ASC, created_at DESC LIMIT ?"
            args.append(limit)
            return [_row_to_dict(r) for r in self._conn.execute(q, args).fetchall()]

    def get_team_expansion(self, proposal_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM team_expansion_proposals WHERE id=?",
                (proposal_id,),
            ).fetchone()
            return _row_to_dict(row) if row else None

    def update_team_expansion(
        self,
        proposal_id: str,
        *,
        promotion_title: str | None = None,
        team_name: str | None = None,
        mission: str | None = None,
        expansion_rationale: str | None = None,
        first_quarter_goals: list[str] | None = None,
        members: list[dict[str, Any]] | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as c:
            row = c.execute(
                "SELECT * FROM team_expansion_proposals WHERE id=? AND status='pending'",
                (proposal_id,),
            ).fetchone()
            if row is None:
                return False
            current = _row_to_dict(row)
            payload = current.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            if promotion_title is not None:
                current["promotion_title"] = promotion_title
                payload["promotion_title"] = promotion_title
            if team_name is not None:
                current["team_name"] = team_name
                payload["team_name"] = team_name
            if mission is not None:
                current["mission"] = mission
                payload["mission"] = mission
            if expansion_rationale is not None:
                payload["expansion_rationale"] = expansion_rationale
            if first_quarter_goals is not None:
                payload["first_quarter_goals"] = first_quarter_goals
            if members is not None:
                payload["members"] = members
            c.execute(
                """UPDATE team_expansion_proposals SET
                   promotion_title=?, team_name=?, mission=?, payload=?, updated_at=?
                   WHERE id=?""",
                (
                    current["promotion_title"],
                    current["team_name"],
                    current["mission"],
                    json.dumps(payload),
                    now,
                    proposal_id,
                ),
            )
            return True

    def resolve_team_expansion(self, proposal_id: str, status: str) -> bool:
        if status not in {"approved", "rejected"}:
            return False
        now = datetime.now(timezone.utc).isoformat()
        with self.transaction() as c:
            cur = c.execute(
                """UPDATE team_expansion_proposals SET status=?, resolved_at=?, updated_at=?
                   WHERE id=? AND status='pending'""",
                (status, now, now, proposal_id),
            )
            if cur.rowcount == 0:
                return False
            c.execute(
                """UPDATE approval_inbox SET status=?, resolved_at=?
                   WHERE id=? AND status='pending'""",
                (status, now, f"exp-{proposal_id}"),
            )
            return True


def _team_expansion_payload(proposal: Any) -> dict[str, Any]:
    members = [
        m.to_context() if hasattr(m, "to_context") else m for m in (proposal.members or [])
    ]
    return {
        "lead_name": proposal.lead_name,
        "lead_role": proposal.lead_role,
        "promotion_title": proposal.promotion_title,
        "team_name": proposal.team_name,
        "mission": proposal.mission,
        "members": members,
        "expansion_rationale": proposal.expansion_rationale,
        "first_quarter_goals": list(proposal.first_quarter_goals or []),
    }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for key in ("payload", "metrics"):
        if key in out and isinstance(out[key], str):
            try:
                out[key] = json.loads(out[key])
            except json.JSONDecodeError:
                pass
    if "approved" in out:
        out["approved"] = bool(out["approved"])
    if "halted" in out:
        out["halted"] = bool(out["halted"])
    if "skipped" in out:
        out["skipped"] = bool(out["skipped"])
    if "pushed" in out:
        out["pushed"] = bool(out["pushed"])
    return out
