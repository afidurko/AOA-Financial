"""Meshed ATTL control plane — constraints + brain + gate + roster + repair."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.attl.critical import CriticalSignal, detect_critical
from aoa.brain.context import brain_context_for_algorithms
from aoa.brain.store import BrainStore
from aoa.constraints import ConstraintSet, load_constraints
from aoa.repair.schedule_gate import evaluate_gate
from aoa.repair.worktree import create_repair_worktree
from aoa.team.kai import KaiAgent
from aoa.team.nova import NovaAgent
from aoa.team.reed import ReedAgent
from aoa.team.roster import TWELVE_MEMBER_ROSTER, roster_names


@dataclass
class MeshSnapshot:
    """Unified view after one mesh sync."""

    constraints: dict[str, Any] = field(default_factory=dict)
    paused: bool = False
    mode: str = "auto-12"
    review_policy: str = "critical_only"
    roster: list[str] = field(default_factory=list)
    brain: dict[str, Any] = field(default_factory=dict)
    algo_context: dict[str, Any] = field(default_factory=dict)
    gate: dict[str, Any] = field(default_factory=dict)
    proposed: dict[str, Any] = field(default_factory=dict)
    selected_task: dict[str, Any] | None = None
    worktree: dict[str, Any] | None = None
    critical: dict[str, Any] = field(default_factory=dict)
    kai: dict[str, Any] = field(default_factory=dict)
    outcome: str = "idle"
    notes: list[str] = field(default_factory=list)
    capture: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraints": self.constraints,
            "paused": self.paused,
            "mode": self.mode,
            "review_policy": self.review_policy,
            "roster": self.roster,
            "brain": self.brain,
            "algo_context_keys": sorted(self.algo_context.keys()),
            "gate": self.gate,
            "proposed": self.proposed,
            "selected_task": self.selected_task,
            "worktree": self.worktree,
            "critical": self.critical,
            "kai": self.kai,
            "outcome": self.outcome,
            "notes": self.notes,
            "capture": self.capture,
        }


class MeshController:
    """Single entry that meshes all ATTL ideas under constraint policy."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        data_dir: Path | None = None,
        llm=None,
    ) -> None:
        self.repo_root = repo_root or Path.cwd()
        self.data_dir = data_dir or (self.repo_root / "data" / "paper" / "attl")
        null = _NullLLM()
        self.nova = NovaAgent(llm or null)
        self.reed = ReedAgent(llm or null)
        self.kai = KaiAgent(llm or null)

    def load_policy(self) -> ConstraintSet:
        return load_constraints(self.repo_root)

    def sync(
        self,
        *,
        dry_run: bool = False,
        report: bool = False,
        create_worktree: bool = True,
        bob_can_proceed: bool | None = None,
        bob_summary: str = "",
        verify_ok: bool | None = None,
    ) -> MeshSnapshot:
        """Full meshed cycle: constraints → brain → gate → propose → critical → worktree."""
        notes: list[str] = []
        cs = self.load_policy()
        snap = MeshSnapshot(
            constraints=cs.to_dict(),
            paused=cs.pause_active,
            mode=cs.mode,
            review_policy=cs.review_policy,
            roster=roster_names(),
        )

        if cs.pause_active:
            snap.outcome = "paused"
            snap.notes = ["Hard floor: loop-pause-all active — mesh halted."]
            snap.capture = str(
                BrainStore.open(self.repo_root).write_capture(
                    "ATTL paused",
                    "loop-pause-all active",
                    critical=True,
                )
            )
            return snap

        brain = self.nova.sync_brain(self.repo_root)
        snap.brain = brain.get("stats") or BrainStore.open(self.repo_root).stats()
        snap.algo_context = brain_context_for_algorithms(self.repo_root)
        notes.append("Nova synced brain mesh into algorithms context.")

        gate = evaluate_gate(repo_root=self.repo_root, mode="repair")
        snap.gate = gate.to_dict()
        notes.append(f"Repair gate: {gate.action.value} — {gate.reason}")

        if gate.action.value == "pause":
            snap.outcome = "paused"
            snap.notes = notes + ["Gate pause — mesh halted."]
            return snap

        repair_items = _load_repair_items(self.repo_root)
        backlog_items = _load_backlog_items(self.repo_root)
        proposed = self.reed.propose_tasks(
            repair_items=repair_items,
            backlog_items=backlog_items,
            out_dir=self.data_dir,
        )
        snap.proposed = {
            "count": proposed.get("count", 0),
            "path": proposed.get("path", ""),
        }
        notes.append(f"Reed proposed {proposed.get('count', 0)} tasks (need-ordered).")

        selected = _select_next_task(
            proposed.get("tasks") or [],
            fixable_ids=set(gate.fixable_items or ()),
        )
        snap.selected_task = selected
        if selected:
            notes.append(f"Selected task: {selected.get('id')} — {selected.get('title')}")

        if bob_can_proceed is None:
            bob_can_proceed, bob_summary = _bob_health(self.repo_root)

        signal: CriticalSignal = detect_critical(
            bob_can_proceed=bob_can_proceed,
            bob_summary=bob_summary,
            gate_action=gate.action.value,
            verify_ok=True if verify_ok is None else verify_ok,
            report_requested=report,
            extra_detail=json.dumps({"selected": selected}, default=str)[:500],
        )
        snap.critical = signal.to_dict()
        kai = self.kai.review_if_needed(signal.to_dict())
        snap.kai = kai

        worktree: dict[str, Any] | None = None
        if (
            create_worktree
            and not dry_run
            and selected
            and selected.get("automatable")
            and gate.action.value == "l2-allowed"
            and not kai.get("engaged")
        ):
            item_id = str(selected.get("id", "task")).replace("/", "-")
            branch = f"repair/{item_id}"
            worktree = create_repair_worktree(
                self.repo_root,
                branch=branch,
                worktrees_dir=self.repo_root / ".aoa-worktrees",
            )
            snap.worktree = worktree
            if worktree.get("ok"):
                notes.append(f"Worktree ready: {worktree.get('path')} ({branch})")
            else:
                signal = detect_critical(
                    bob_can_proceed=bob_can_proceed,
                    bob_summary=bob_summary,
                    gate_action=gate.action.value,
                    worktree_ok=False,
                    report_requested=report,
                )
                snap.critical = signal.to_dict()
                kai = self.kai.review_if_needed(signal.to_dict())
                snap.kai = kai
                notes.append(f"Worktree failed — Kai path: {worktree.get('error')}")

        if kai.get("engaged"):
            snap.outcome = "critical-report"
            notes.append(f"Kai engaged: {kai.get('summary')}")
            if dry_run:
                notes.append("Dry-run — no worktree/PR side effects.")
        elif dry_run:
            snap.outcome = "dry-run"
            notes.append("Dry-run — no worktree/PR side effects.")
        elif gate.action.value != "l2-allowed":
            snap.outcome = "gate-blocked"
            notes.append("Gate blocked coding side effects; brain+propose still ran.")
        elif selected and selected.get("automatable"):
            snap.outcome = "auto-continue"
            notes.append(
                "Auto-12 continue: Kai skipped. Maker may implement in worktree; "
                "draft PR only; user merges."
            )
        else:
            snap.outcome = "auto-continue"
            notes.append("No automatable task — mesh idle after propose.")

        store = BrainStore.open(self.repo_root)
        snap.capture = str(
            store.write_capture(
                "ATTL mesh sync",
                (
                    f"outcome: {snap.outcome}\n"
                    f"mode: {snap.mode}\n"
                    f"gate: {gate.action.value}\n"
                    f"proposed: {snap.proposed.get('count', 0)}\n"
                    f"selected: {(selected or {}).get('id', '')}\n"
                    f"kai: {kai.get('verdict')}\n"
                    f"roster: {len(TWELVE_MEMBER_ROSTER)}\n"
                    f"notes:\n"
                    + "\n".join(f"- {n}" for n in notes)
                ),
                critical=bool(kai.get("engaged")),
            )
        )
        _append_run_log(
            self.repo_root,
            outcome=snap.outcome,
            note=f"attl mesh selected={(selected or {}).get('id', '-')} kai={kai.get('verdict')}",
        )
        snap.notes = notes
        return snap


class _NullLLM:
    def structured(self, system: str, prompt: str, schema: dict, **kwargs):  # noqa: ANN001
        raise RuntimeError("LLM not configured")


def _select_next_task(
    tasks: list[dict[str, Any]],
    *,
    fixable_ids: set[str],
) -> dict[str, Any] | None:
    """Prefer repair items in gate fixable set, else first automatable."""
    if not tasks:
        return None
    for task in tasks:
        if not task.get("automatable"):
            continue
        tid = str(task.get("id", ""))
        raw = tid.removeprefix("repair-")
        if fixable_ids and (raw in fixable_ids or tid in fixable_ids):
            return task
    for task in tasks:
        if not task.get("automatable"):
            continue
        tid = str(task.get("id", ""))
        if tid.startswith("repair-") and fixable_ids:
            raw = tid.removeprefix("repair-")
            if raw not in fixable_ids and tid not in fixable_ids:
                continue
        return task
    return None


def _bob_health(repo_root: Path) -> tuple[bool, str]:
    try:
        from aoa.team.code_engineering import run_code_quality_audit

        report = run_code_quality_audit(repo_root=repo_root)
        return bool(report.can_proceed), report.summary
    except Exception as exc:  # noqa: BLE001
        return False, f"Bob audit failed: {exc}"


def _load_repair_items(repo_root: Path) -> list[dict[str, Any]]:
    candidates = [
        repo_root / "loop-state" / "repair-queue.json",
        repo_root / "data" / "paper" / "repair" / "queue.json",
        repo_root / "data" / "paper-dry" / "repair" / "queue.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            items = data.get("items") or data.get("queue") or []
            if isinstance(items, dict):
                return [
                    {"id": k, **v} if isinstance(v, dict) else {"id": k}
                    for k, v in items.items()
                ]
            return [x for x in items if isinstance(x, dict)]
    return []


def _load_backlog_items(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "docs" / "upgrade-backlog.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = data.get("items") or {}
    return [{"id": k, **v} for k, v in items.items() if isinstance(v, dict)]


def _append_run_log(repo_root: Path, *, outcome: str, note: str) -> None:
    path = repo_root / "loop-run-log.md"
    if not path.is_file():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    row = f"| {stamp} | attl | L2 | {outcome} | {note} |\n"
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + row, encoding="utf-8")
