"""Tests for the ship-ready task loop agent."""

from __future__ import annotations

from pathlib import Path

from aoa.ship.loop import (
    IssueStatus,
    ShipIssue,
    ShipLoopAgent,
    ShipLoopState,
    load_state,
    save_state,
)


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
