"""Tests for loop automation schedule gate."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from aoa.repair.schedule_gate import (
    GateAction,
    count_runs_by_loop,
    evaluate_gate,
    fixable_queue_titles,
    is_paused,
    l2_enabled_in_state,
)


def test_is_paused_detects_high_priority_flag(tmp_path: Path):
    state = tmp_path / "STATE.md"
    state.write_text(
        "## High Priority\n\n- loop-pause-all — stop automations\n",
        encoding="utf-8",
    )
    assert is_paused(state) is True


def test_l2_enabled_in_state_section(tmp_path: Path):
    state = tmp_path / "STATE.md"
    state.write_text(
        "## Loop automation\n\n- L2: enabled\n",
        encoding="utf-8",
    )
    assert l2_enabled_in_state(state) is True


def test_count_runs_by_loop_last_24h(tmp_path: Path):
    log = tmp_path / "loop-run-log.md"
    log.write_text(
        "| Timestamp (UTC) | Loop | Level | Outcome | Notes |\n"
        "|-----------------|------|-------|---------|-------|\n"
        "| 2026-07-04 18:47 | fable-repair | L2 | report-only | tokens_estimate=6000 |\n"
        "| 2026-07-03 10:00 | daily-triage | L1 | report-only | old |\n",
        encoding="utf-8",
    )
    now = datetime(2026, 7, 4, 19, 0, tzinfo=timezone.utc)
    counts = count_runs_by_loop(log, now=now)
    assert counts == {"fable-repair": 1}


def test_fixable_queue_titles(tmp_path: Path):
    queue = tmp_path / "queue.json"
    queue.write_text(
        '{"items": ['
        '{"title": "Verify failed: pytest", "fixable": true, "status": "queued"},'
        '{"title": "PR #29", "fixable": false, "status": "queued"}'
        "]}",
        encoding="utf-8",
    )
    assert fixable_queue_titles(queue) == ("Verify failed: pytest",)


def test_evaluate_gate_l1_when_l2_not_enabled(tmp_path: Path):
    (tmp_path / "STATE.md").write_text("# Loop State\n\n## Watch List\n\n- ok\n", encoding="utf-8")
    (tmp_path / "loop-run-log.md").write_text(
        "| Timestamp (UTC) | Loop | Level | Outcome | Notes |\n"
        "|-----------------|------|-------|---------|-------|\n",
        encoding="utf-8",
    )
    queue_dir = tmp_path / "data" / "paper-dry" / "repair"
    queue_dir.mkdir(parents=True)
    (queue_dir / "queue.json").write_text(
        '{"items": [{"title": "x", "fixable": true, "status": "queued"}]}',
        encoding="utf-8",
    )
    result = evaluate_gate(repo_root=tmp_path)
    assert result.action is GateAction.L1_ONLY
    assert "L2 automation not enabled" in result.reason


def test_evaluate_gate_triage_ok(tmp_path: Path):
    (tmp_path / "STATE.md").write_text("# Loop State\n", encoding="utf-8")
    (tmp_path / "loop-run-log.md").write_text(
        "| Timestamp (UTC) | Loop | Level | Outcome | Notes |\n"
        "|-----------------|------|-------|---------|-------|\n",
        encoding="utf-8",
    )
    result = evaluate_gate(repo_root=tmp_path, mode="triage")
    assert result.action is GateAction.TRIAGE_OK
