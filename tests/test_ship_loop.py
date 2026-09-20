"""Tests for the ship-ready task loop agent."""

from __future__ import annotations

from pathlib import Path

from aoa.ship.loop import (
    CONFLICT_MARKER_PATHS,
    IssueStatus,
    ShipIssue,
    ShipLoopAgent,
    ShipLoopState,
    load_state,
    save_state,
)


def test_conflict_marker_scan_includes_pyproject():
    assert "pyproject.toml" in CONFLICT_MARKER_PATHS
    assert "src" in CONFLICT_MARKER_PATHS
    assert "tests" in CONFLICT_MARKER_PATHS
    assert "scripts" in CONFLICT_MARKER_PATHS
    assert "docs" in CONFLICT_MARKER_PATHS
    assert "requirements.txt" in CONFLICT_MARKER_PATHS
    assert "loop-prompts.yaml" in CONFLICT_MARKER_PATHS


def test_ship_state_roundtrip(tmp_path: Path):
    path = tmp_path / "ship-loop.json"
    state = ShipLoopState(
        branch="cursor/test",
        pr_number=60,
        issues=[
            ShipIssue(
                id="lint",
                title="lint",
                kind=__import__("aoa.ship.loop", fromlist=["IssueKind"]).IssueKind.LINT,
            )
        ],
    )
    save_state(state, path)
    loaded = load_state(path)
    assert loaded.branch == "cursor/test"
    assert loaded.pr_number == 60
    assert loaded.issues[0].id == "lint"


def test_mark_ready_requires_proofread(tmp_path: Path):
    root = tmp_path
    (root / "src").mkdir()
    (root / "tests").mkdir()
    agent = ShipLoopAgent(root, state_path=tmp_path / "ship.json")
    # Seed empty-open queue with proofread open
    from aoa.ship.loop import IssueKind

    state = ShipLoopState(
        branch="x",
        issues=[
            ShipIssue(id="proofread", title="proof", kind=IssueKind.PROOFREAD),
        ],
    )
    save_state(state, agent.state_path)
    ok, msg = agent.can_mark_ready()
    assert ok is False
    assert "Open" in msg or "Proofread" in msg


def test_mark_fixed_and_ready_gate(tmp_path: Path):
    from aoa.ship.loop import IssueKind, ProofreadReport

    agent = ShipLoopAgent(tmp_path, state_path=tmp_path / "ship.json")
    state = ShipLoopState(
        branch="x",
        issues=[
            ShipIssue(
                id="roster-jim-cindy",
                title="roster",
                kind=IssueKind.ROSTER,
                status=IssueStatus.FIXED,
            ),
            ShipIssue(
                id="proofread",
                title="proof",
                kind=IssueKind.PROOFREAD,
                status=IssueStatus.FIXED,
            ),
        ],
        proofread=ProofreadReport(ok=True, ruff_ok=True, pytest_ok=True, notes=["ok"]),
    )
    save_state(state, agent.state_path)
    ok, msg = agent.can_mark_ready()
    assert ok is True
    ready = agent.mark_ready()
    assert ready.ready_for_merge is True


def test_attempt_blocks_after_max(tmp_path: Path):
    from aoa.ship.loop import IssueKind

    agent = ShipLoopAgent(tmp_path, state_path=tmp_path / "ship.json")
    state = ShipLoopState(
        branch="x",
        issues=[ShipIssue(id="lint", title="lint", kind=IssueKind.LINT)],
    )
    save_state(state, agent.state_path)
    for _ in range(3):
        agent.mark_attempt("lint")
    loaded = load_state(agent.state_path)
    assert loaded.issues[0].status is IssueStatus.BLOCKED
    assert loaded.issues[0].attempts == 3


def test_mark_fixed_unknown_id_raises(tmp_path: Path):
    import pytest

    agent = ShipLoopAgent(tmp_path, state_path=tmp_path / "ship.json")
    save_state(ShipLoopState(branch="x", issues=[]), agent.state_path)
    with pytest.raises(ValueError, match="unknown ship issue"):
        agent.mark_fixed("missing")
    with pytest.raises(ValueError, match="unknown ship issue"):
        agent.mark_attempt("missing")


def test_run_missing_command_returns_127(tmp_path: Path):
    from aoa.ship.loop import _run

    proc = _run(["definitely-not-a-real-binary-aoa-xyz"], cwd=tmp_path)
    assert proc.returncode == 127
    assert "not found" in (proc.stderr or "").lower()


def test_discover_clears_stale_proofread(tmp_path: Path, monkeypatch):
    from aoa.ship.loop import IssueKind, ProofreadReport

    agent = ShipLoopAgent(tmp_path, state_path=tmp_path / "ship.json")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    state = ShipLoopState(
        branch="x",
        issues=[
            ShipIssue(
                id="proofread",
                title="proof",
                kind=IssueKind.PROOFREAD,
                status=IssueStatus.FIXED,
            )
        ],
        proofread=ProofreadReport(ok=True, ruff_ok=True, pytest_ok=True, notes=["stale"]),
    )
    save_state(state, agent.state_path)

    def fake_run(cmd, *, cwd):
        import subprocess

        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("aoa.ship.loop._run", fake_run)
    monkeypatch.setattr(agent, "current_branch", lambda: "x")
    refreshed = agent.discover()
    assert refreshed.proofread is None
    proof = next(i for i in refreshed.issues if i.id == "proofread")
    assert proof.status is IssueStatus.OPEN
    ok, _msg = agent.can_mark_ready()
    assert ok is False
