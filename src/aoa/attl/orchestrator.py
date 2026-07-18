"""ATTL auto-12 orchestrator — critical-only review."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aoa.attl.critical import detect_critical
from aoa.brain.context import brain_context_for_algorithms
from aoa.brain.store import BrainStore, ensure_brain_workspace
from aoa.team.kai import KaiAgent
from aoa.team.nova import NovaAgent
from aoa.team.reed import ReedAgent
from aoa.team.roster import TWELVE_MEMBER_ROSTER, roster_names


@dataclass
class AttlRunResult:
    mode: str = "auto-12"
    dry_run: bool = False
    roster: list[str] = field(default_factory=list)
    brain_stats: dict[str, Any] = field(default_factory=dict)
    proposed: dict[str, Any] = field(default_factory=dict)
    critical: dict[str, Any] = field(default_factory=dict)
    kai: dict[str, Any] = field(default_factory=dict)
    algo_context_keys: list[str] = field(default_factory=list)
    capture: str = ""
    outcome: str = "auto-continue"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "dry_run": self.dry_run,
            "roster": self.roster,
            "brain_stats": self.brain_stats,
            "proposed": self.proposed,
            "critical": self.critical,
            "kai": self.kai,
            "algo_context_keys": self.algo_context_keys,
            "capture": self.capture,
            "outcome": self.outcome,
            "notes": self.notes,
        }


class AttlOrchestrator:
    """Run auto ATTL cycle with Nova → Reed → (Kai if critical)."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        data_dir: Path | None = None,
        llm=None,
    ) -> None:
        self.repo_root = repo_root or Path.cwd()
        self.data_dir = data_dir or (self.repo_root / "data" / "paper" / "attl")
        self.llm = llm
        self.nova = NovaAgent(llm) if llm is not None else NovaAgent(_NullLLM())
        self.reed = ReedAgent(llm) if llm is not None else ReedAgent(_NullLLM())
        self.kai = KaiAgent(llm) if llm is not None else KaiAgent(_NullLLM())

    def init_workspace(self) -> dict[str, Any]:
        brain = ensure_brain_workspace(self.repo_root)
        store = BrainStore.open(self.repo_root)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = self.data_dir / "config.json"
        if not cfg_path.is_file():
            cfg_path.write_text(
                json.dumps(
                    {
                        "mode": "auto-12",
                        "review_policy": "critical_only",
                        "roster_size": len(TWELVE_MEMBER_ROSTER),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        return {
            "brain": str(brain),
            "mode": store.mode,
            "roster": roster_names(),
            "stats": store.stats(),
            "config": str(cfg_path),
        }

    def status(self) -> dict[str, Any]:
        store = BrainStore.open(self.repo_root)
        cfg = {}
        cfg_path = self.data_dir / "config.json"
        if cfg_path.is_file():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return {
            "mode": cfg.get("mode") or store.mode,
            "review_policy": cfg.get("review_policy", "critical_only"),
            "roster": roster_names(),
            "roster_size": len(TWELVE_MEMBER_ROSTER),
            "brain": store.stats(),
            "pending_tasks": _count_proposed(self.data_dir),
        }

    def roster(self) -> list[dict[str, str]]:
        return [
            {"name": m.name, "role": m.role, "slug": m.slug}
            for m in TWELVE_MEMBER_ROSTER
        ]

    def propose(self) -> dict[str, Any]:
        repair_items = _load_repair_items(self.repo_root)
        backlog_items = _load_backlog_items(self.repo_root)
        return self.reed.propose_tasks(
            repair_items=repair_items,
            backlog_items=backlog_items,
            out_dir=self.data_dir,
        )

    def brain_sync(self) -> dict[str, Any]:
        return self.nova.sync_brain(self.repo_root)

    def run(
        self,
        *,
        dry_run: bool = False,
        report: bool = False,
        bob_can_proceed: bool | None = True,
        bob_summary: str = "",
        gate_action: str = "l2-allowed",
        verify_ok: bool | None = True,
    ) -> AttlRunResult:
        init = self.init_workspace()
        brain = self.brain_sync()
        proposed = self.propose()
        algo_ctx = brain_context_for_algorithms(self.repo_root)

        signal = detect_critical(
            bob_can_proceed=bob_can_proceed,
            bob_summary=bob_summary,
            gate_action=gate_action,
            verify_ok=verify_ok,
            report_requested=report,
        )
        kai = self.kai.review_if_needed(signal.to_dict())

        outcome = "auto-continue"
        notes = [
            "Mode auto-12: process review skipped unless critical.",
            f"Reed proposed {proposed.get('count', 0)} tasks (need-ordered).",
        ]
        if dry_run:
            outcome = "dry-run"
            notes.append("Dry-run — no worktree/PR side effects.")
        elif kai.get("engaged"):
            outcome = "critical-report"
            notes.append(f"Kai engaged: {kai.get('summary')}")
        else:
            notes.append("Kai skipped — no critical flaw / system failure / report.")

        store = BrainStore.open(self.repo_root)
        capture = store.write_capture(
            "ATTL run",
            (
                f"outcome: {outcome}\n"
                f"proposed: {proposed.get('count', 0)}\n"
                f"kai: {kai.get('verdict')}\n"
                f"dry_run: {dry_run}\n"
            ),
            critical=bool(kai.get("engaged")),
        )

        return AttlRunResult(
            mode=str(init.get("mode") or "auto-12"),
            dry_run=dry_run,
            roster=roster_names(),
            brain_stats=brain.get("stats") or store.stats(),
            proposed={"count": proposed.get("count", 0), "path": proposed.get("path", "")},
            critical=signal.to_dict(),
            kai=kai,
            algo_context_keys=sorted(algo_ctx.keys()),
            capture=str(capture),
            outcome=outcome,
            notes=notes,
        )


class _NullLLM:
    """Placeholder when no LLM is wired — agents use deterministic paths."""

    def structured(self, system: str, prompt: str, schema: dict, **kwargs):  # noqa: ANN001
        raise RuntimeError("LLM not configured for ATTL structured calls")


def _count_proposed(data_dir: Path) -> int:
    path = data_dir / "proposed-tasks.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    return len(data.get("tasks") or [])


def _load_repair_items(repo_root: Path) -> list[dict[str, Any]]:
    candidates = [
        repo_root / "loop-state" / "repair-queue.json",
        repo_root / "data" / "paper" / "repair" / "queue.json",
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
                return [{"id": k, **v} if isinstance(v, dict) else {"id": k} for k, v in items.items()]
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
    out: list[dict[str, Any]] = []
    for key, val in items.items():
        if isinstance(val, dict):
            row = {"id": key, **val}
            out.append(row)
    return out
