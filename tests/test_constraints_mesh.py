"""Constraints loader + ATTL mesh integration."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from aoa.attl.mesh import MeshController, _select_next_task
from aoa.constraints import load_constraints
from aoa.team.roster import TWELVE_MEMBER_ROSTER


def test_load_constraints_hard_floor_and_auto12():
    cs = load_constraints(Path.cwd())
    assert cs.mode == "auto-12"
    assert cs.review_policy == "critical_only"
    assert cs.rule_count >= 8
    assert any("loop-pause-all" in r.lower() or "pause" in r.lower() for r in cs.hard_floor)
    assert any(".env" in r for r in cs.hard_floor)
    assert cs.pause_active is False


def test_select_next_task_prefers_fixable_repair():
    tasks = [
        {"id": "upg-x", "automatable": True, "title": "backlog"},
        {"id": "repair-abc", "automatable": True, "title": "fix me"},
        {"id": "repair-zzz", "automatable": False, "title": "human"},
    ]
    picked = _select_next_task(tasks, fixable_ids={"abc"})
    assert picked is not None
    assert picked["id"] == "repair-abc"


def test_mesh_controller_dry_run(tmp_path: Path):
    _seed_repo(tmp_path)
    ctrl = MeshController(repo_root=tmp_path, data_dir=tmp_path / "data" / "attl")
    snap = ctrl.sync(dry_run=True, bob_can_proceed=True, create_worktree=False)
    assert snap.paused is False
    assert snap.mode == "auto-12"
    assert len(snap.roster) == 12
    assert snap.outcome == "dry-run"
    assert snap.kai.get("engaged") is False
    assert snap.proposed.get("count", 0) >= 1
    assert snap.brain.get("members") == 12


def test_mesh_pause_halts(tmp_path: Path):
    _seed_repo(tmp_path, pause=True)
    ctrl = MeshController(repo_root=tmp_path, data_dir=tmp_path / "data" / "attl")
    snap = ctrl.sync(dry_run=True, bob_can_proceed=True)
    assert snap.outcome == "paused"
    assert snap.paused is True


def test_team_orchestrator_has_attl_agents(fake_broker, fake_llm):
    from aoa.config import Config, RiskLimits
    from aoa.team.orchestrator import TeamOrchestrator

    cfg = Config(
        broker="moomoo",
        anthropic_api_key="x",
        universe=("AAPL",),
        dry_run=True,
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )
    team = TeamOrchestrator(cfg, fake_broker, fake_llm)
    assert team.nova.display_name == "Nova"
    assert team.reed.display_name == "Reed"
    assert team.kai.display_name == "Kai"
    assert len(TWELVE_MEMBER_ROSTER) == 12


def _seed_repo(root: Path, *, pause: bool = False) -> None:
    from aoa.team.roster import TWELVE_MEMBER_ROSTER

    state = "## Loop automation\n\n- L1: enabled\n- L2: enabled\n"
    if pause:
        state = "## High Priority\n\n- **loop-pause-all** — test\n\n" + state
    (root / "STATE.md").write_text(state, encoding="utf-8")
    (root / "loop-run-log.md").write_text(
        "| Timestamp (UTC) | Loop | Level | Outcome | Notes |\n"
        "|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    (root / "loop-constraints.md").write_text(
        Path.cwd().joinpath("loop-constraints.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    mesh = {
        "version": 1,
        "mode": "auto-12",
        "members": [
            {"id": m.slug, "name": m.name, "role": m.role, "feeds": []}
            for m in TWELVE_MEMBER_ROSTER
        ],
        "algorithms": [{"id": "algo.julie", "owner": "julie"}],
        "spines": [],
    }
    for rel in (
        "_CLAUDE.md",
        "README.md",
        "spine/ATTL.md",
        "spine/Algorithms.md",
        "spine/Team-Mesh.md",
    ):
        path = root / "brain" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test\n", encoding="utf-8")
    (root / "brain" / "captures").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "decisions").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "mesh").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "mesh" / "index.yaml").write_text(yaml.safe_dump(mesh), encoding="utf-8")
    (root / "brain" / "mesh" / "repos.yaml").write_text(
        yaml.safe_dump({"repos": []}), encoding="utf-8"
    )
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "upgrade-backlog.json").write_text(
        json.dumps(
            {
                "items": {
                    "upg-x": {
                        "title": "Test item",
                        "automatable": True,
                        "skill": "minimal-fix",
                        "detail": "x",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
