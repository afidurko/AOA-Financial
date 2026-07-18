"""ATTL auto-12 orchestrator — delegates to meshed MeshController."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aoa.attl.mesh import MeshController, MeshSnapshot
from aoa.brain.store import BrainStore, ensure_brain_workspace
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
    gate: dict[str, Any] = field(default_factory=dict)
    selected_task: dict[str, Any] | None = None
    worktree: dict[str, Any] | None = None
    algo_context_keys: list[str] = field(default_factory=list)
    capture: str = ""
    outcome: str = "auto-continue"
    notes: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "dry_run": self.dry_run,
            "roster": self.roster,
            "brain_stats": self.brain_stats,
            "proposed": self.proposed,
            "critical": self.critical,
            "kai": self.kai,
            "gate": self.gate,
            "selected_task": self.selected_task,
            "worktree": self.worktree,
            "algo_context_keys": self.algo_context_keys,
            "capture": self.capture,
            "outcome": self.outcome,
            "notes": self.notes,
            "constraints": self.constraints,
        }

    @classmethod
    def from_mesh(cls, snap: MeshSnapshot, *, dry_run: bool) -> AttlRunResult:
        return cls(
            mode=snap.mode,
            dry_run=dry_run,
            roster=snap.roster,
            brain_stats=snap.brain,
            proposed=snap.proposed,
            critical=snap.critical,
            kai=snap.kai,
            gate=snap.gate,
            selected_task=snap.selected_task,
            worktree=snap.worktree,
            algo_context_keys=sorted(snap.algo_context.keys()),
            capture=snap.capture,
            outcome=snap.outcome,
            notes=snap.notes,
            constraints=snap.constraints,
        )


class AttlOrchestrator:
    """Thin facade over MeshController (constraints + brain + gate + Reed + Kai)."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        data_dir: Path | None = None,
        llm=None,
    ) -> None:
        self.repo_root = repo_root or Path.cwd()
        self.data_dir = data_dir or (self.repo_root / "data" / "paper" / "attl")
        self.mesh = MeshController(
            repo_root=self.repo_root,
            data_dir=self.data_dir,
            llm=llm,
        )
        self.reed = self.mesh.reed
        self.nova = self.mesh.nova
        self.kai = self.mesh.kai

    def init_workspace(self) -> dict[str, Any]:
        brain = ensure_brain_workspace(self.repo_root)
        store = BrainStore.open(self.repo_root)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = self.data_dir / "config.json"
        policy = self.mesh.load_policy()
        cfg = {
            "mode": policy.mode,
            "review_policy": policy.review_policy,
            "roster_size": len(TWELVE_MEMBER_ROSTER),
            "hard_floor_rules": len(policy.hard_floor),
            "meshed": True,
        }
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return {
            "brain": str(brain),
            "mode": store.mode,
            "roster": roster_names(),
            "stats": store.stats(),
            "config": str(cfg_path),
            "constraints": policy.to_dict(),
        }

    def status(self) -> dict[str, Any]:
        store = BrainStore.open(self.repo_root)
        policy = self.mesh.load_policy()
        cfg: dict[str, Any] = {}
        cfg_path = self.data_dir / "config.json"
        if cfg_path.is_file():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return {
            "mode": cfg.get("mode") or policy.mode,
            "review_policy": cfg.get("review_policy") or policy.review_policy,
            "roster": roster_names(),
            "roster_size": len(TWELVE_MEMBER_ROSTER),
            "brain": store.stats(),
            "pending_tasks": _count_proposed(self.data_dir),
            "paused": policy.pause_active,
            "hard_floor_rules": len(policy.hard_floor),
            "meshed": True,
        }

    def roster(self) -> list[dict[str, str]]:
        return [
            {"name": m.name, "role": m.role, "slug": m.slug}
            for m in TWELVE_MEMBER_ROSTER
        ]

    def propose(self) -> dict[str, Any]:
        from aoa.attl.mesh import _load_backlog_items, _load_repair_items

        return self.reed.propose_tasks(
            repair_items=_load_repair_items(self.repo_root),
            backlog_items=_load_backlog_items(self.repo_root),
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
        """Run meshed cycle.

        When bob_can_proceed is explicitly True/False (tests), MeshController uses it.
        Pass None to force live Bob audit (production CLI).
        """
        # Preserve test override API: default True means "assume healthy" for unit tests;
        # CLI passes bob_can_proceed=None for live health.
        snap = self.mesh.sync(
            dry_run=dry_run,
            report=report,
            create_worktree=not dry_run,
            bob_can_proceed=bob_can_proceed,
            bob_summary=bob_summary,
            verify_ok=verify_ok,
        )
        # If caller forced a gate_action for tests via unused param, ignore — mesh uses real gate.
        _ = gate_action
        return AttlRunResult.from_mesh(snap, dry_run=dry_run)


def _count_proposed(data_dir: Path) -> int:
    path = data_dir / "proposed-tasks.json"
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    return len(data.get("tasks") or [])


# Re-export for tests that imported helpers from orchestrator historically
def _load_repair_items(repo_root: Path) -> list[dict[str, Any]]:
    from aoa.attl.mesh import _load_repair_items as _impl

    return _impl(repo_root)
