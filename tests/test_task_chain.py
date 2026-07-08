"""Tests for upgrade backlog task chaining."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa.loop.task_chain import (
    ChainAction,
    advance_chain,
    bootstrap_chain_from_state,
    load_backlog,
    resolve_next_automatable,
)


@pytest.fixture
def mini_repo(tmp_path: Path) -> Path:
    backlog = {
        "recommended_sequence": ["upg-h", "upg-a", "upg-b"],
        "assumed_completed": [],
        "items": {
            "upg-h": {
                "title": "Human step",
                "skill": "human",
                "automatable": False,
                "detail": "you do it",
            },
            "upg-a": {
                "title": "Auto A",
                "skill": "minimal-fix",
                "automatable": True,
                "detail": "fix A",
            },
            "upg-b": {
                "title": "Auto B",
                "skill": "minimal-fix",
                "automatable": True,
                "detail": "fix B",
            },
        },
    }
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "upgrade-backlog.json").write_text(
        json.dumps(backlog), encoding="utf-8"
    )
    (tmp_path / "STATE.md").write_text(
        "# Loop State\n\n"
        "## High Priority (loop is acting or waiting on human)\n\n"
        "- **old** — item\n\n"
        "## Watch List\n\n- ok\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "src" / "aoa").mkdir(parents=True)
    return tmp_path


def test_load_backlog(mini_repo: Path):
    sequence, items, assumed = load_backlog(mini_repo)
    assert sequence == ["upg-h", "upg-a", "upg-b"]
    assert assumed == []
    assert items["upg-a"].automatable is True


def test_resolve_skips_human_first(mini_repo: Path):
    sequence, items, _ = load_backlog(mini_repo)
    next_id, skipped = resolve_next_automatable(
        sequence, items, completed=set(), skipped_human=set()
    )
    assert next_id == "upg-a"
    assert skipped == ("upg-h",)


def test_advance_queues_next(mini_repo: Path):
    result = advance_chain("upg-a", repo_root=mini_repo, env="test")
    assert result.action is ChainAction.QUEUED
    assert result.next_id == "upg-b"
    state_text = (mini_repo / "STATE.md").read_text(encoding="utf-8")
    assert "Auto B" in state_text
    assert "upg-b" in state_text


def test_advance_after_last_automatable_alerts_human(mini_repo: Path):
    advance_chain("upg-a", repo_root=mini_repo, env="test")
    result = advance_chain("upg-b", repo_root=mini_repo, env="test")
    assert result.action is ChainAction.ALERT_HUMAN
    assert result.exit_code == 3


def test_bootstrap_uses_assumed_completed(tmp_path: Path):
    backlog = {
        "recommended_sequence": ["upg-h", "upg-a", "upg-b"],
        "assumed_completed": ["upg-a"],
        "items": {
            "upg-h": {"title": "H", "skill": "human", "automatable": False, "detail": "h"},
            "upg-a": {"title": "A", "skill": "minimal-fix", "automatable": True, "detail": "a"},
            "upg-b": {"title": "B", "skill": "minimal-fix", "automatable": True, "detail": "b"},
        },
    }
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "upgrade-backlog.json").write_text(
        json.dumps(backlog), encoding="utf-8"
    )
    (tmp_path / "STATE.md").write_text(
        "# Loop State\n\n## High Priority (loop is acting or waiting on human)\n\n_x_\n\n## Watch List\n\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "src" / "aoa").mkdir(parents=True)
    state = bootstrap_chain_from_state(tmp_path, env="test")
    assert state.current == "upg-b"
    assert "upg-a" in state.completed
