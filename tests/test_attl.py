"""Tests for ATTL auto-12, brain mesh, and critical-only review."""

from __future__ import annotations

import json
from pathlib import Path

from aoa.attl.critical import detect_critical
from aoa.attl.orchestrator import AttlOrchestrator
from aoa.brain.context import brain_context_for_algorithms, format_brain_context_prompt
from aoa.brain.store import BrainStore, ensure_brain_workspace
from aoa.team.aaron import _ensure_roster
from aoa.team.kai import KaiAgent
from aoa.team.models import TeamMemberStatus
from aoa.team.roster import TWELVE_MEMBER_ROSTER, roster_names


def test_twelve_member_roster_unique():
    assert len(TWELVE_MEMBER_ROSTER) == 12
    names = roster_names()
    assert len(set(names)) == 12
    assert {"Nova", "Reed", "Kai"} <= set(names)
    assert names[0] == "Tom"
    assert names[-1] == "Kai"


def test_aaron_ensure_roster_includes_twelve():
    filled = _ensure_roster(
        [TeamMemberStatus(name="Tom", role="Trend Analyst", completed=True, notes="ok")]
    )
    assert len(filled) == 12
    by_name = {m.name: m for m in filled}
    assert by_name["Tom"].completed is True
    assert by_name["Nova"].completed is False
    assert by_name["Reed"].role.startswith("Task-Loop")
    assert by_name["Kai"].role.startswith("Critical")


def test_critical_detector_and_kai_skip(tmp_path: Path):
    ok = detect_critical(bob_can_proceed=True, verify_ok=True, gate_action="l2-allowed")
    assert ok.needs_review is False
    kai = KaiAgent(_Null())
    skipped = kai.review_if_needed(ok.to_dict())
    assert skipped["engaged"] is False
    assert skipped["verdict"] == "skip"

    bad = detect_critical(bob_can_proceed=False, bob_summary="imports broken")
    assert bad.critical is True
    engaged = kai.review_if_needed(bad.to_dict())
    assert engaged["engaged"] is True
    assert engaged["verdict"] == "report"


def test_brain_workspace_and_algo_context():
    # Use repo brain/ checked into the tree
    root = Path.cwd()
    ensure_brain_workspace(root)
    store = BrainStore.open(root)
    assert store.required_paths_ok()
    assert store.mode == "auto-12"
    assert len(store.members) == 12
    ctx = brain_context_for_algorithms(root)
    assert ctx["source"] == "aoa.brain"
    assert "algo.julie" in [a["id"] for a in ctx["algorithms"]]
    prompt = format_brain_context_prompt(ctx)
    assert "Second-brain mesh context" in prompt


def test_attl_orchestrator_auto_continue(tmp_path: Path):
    # Minimal brain skeleton + STATE so mesh gate can resolve
    _seed_brain(tmp_path)
    (tmp_path / "STATE.md").write_text(
        "## Loop automation\n\n- L1: enabled\n- L2: enabled\n",
        encoding="utf-8",
    )
    (tmp_path / "loop-run-log.md").write_text(
        "| Timestamp (UTC) | Loop | Level | Outcome | Notes |\n|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    (tmp_path / "loop-constraints.md").write_text(
        Path.cwd().joinpath("loop-constraints.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "upgrade-backlog.json").write_text(
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
    orch = AttlOrchestrator(repo_root=tmp_path, data_dir=tmp_path / "data" / "attl")
    init = orch.init_workspace()
    assert len(init["roster"]) == 12
    assert init["constraints"]["mode"] == "auto-12"
    result = orch.run(dry_run=True, bob_can_proceed=True)
    assert result.outcome == "dry-run"
    assert result.kai["engaged"] is False
    assert result.proposed["count"] >= 1

    reported = orch.run(report=True, bob_can_proceed=True, dry_run=True)
    assert reported.kai["engaged"] is True
    assert reported.outcome == "critical-report"
    assert reported.critical.get("report_requested") is True


def test_cli_attl_roster(monkeypatch, capsys):
    from aoa.cli import main
    from aoa.config import Config

    monkeypatch.setattr("aoa.cli.Config.from_env", lambda: Config(env="test", anthropic_api_key="x"))
    code = main(["attl", "roster"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Nova" in out
    assert "Reed" in out
    assert "Kai" in out


class _Null:
    def structured(self, *args, **kwargs):
        raise RuntimeError("unused")


def _seed_brain(root: Path) -> None:
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
    import yaml

    (root / "brain" / "mesh").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "mesh" / "index.yaml").write_text(
        yaml.safe_dump(mesh), encoding="utf-8"
    )
    (root / "brain" / "mesh" / "repos.yaml").write_text(
        yaml.safe_dump({"repos": []}), encoding="utf-8"
    )
