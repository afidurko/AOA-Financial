"""Tests for the autonomous work-loop orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa.config import Config
from aoa.workloop.adapt import write_adaptations
from aoa.workloop.approval import ApprovalRequired, check_approval, record_approval
from aoa.workloop.discover import discover_sources
from aoa.workloop.extract import extract_insights
from aoa.workloop.models import STAGE_ORDER
from aoa.workloop.orchestrator import WorkloopOrchestrator
from aoa.workloop.propose import build_proposal
from aoa.workloop.store import WorkloopStore
from aoa.workloop.stages import default_stages


def _config(tmp_path: Path, **kwargs) -> Config:
    defaults = dict(
        env="test",
        data_dir=tmp_path / "data",
        journal_path=tmp_path / "journal.jsonl",
        plasticity_path=tmp_path / "plasticity.json",
        workloop_path=tmp_path / "workloop",
        workloop_approver="Aaron",
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
    )
    defaults.update(kwargs)
    return Config(**defaults)


def test_default_workloop_has_ten_stages():
    names = [s.name for s in default_stages()]
    assert names == list(STAGE_ORDER)


def test_discover_sources_finds_core_materials(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    cfg = _config(tmp_path, journal_path=repo / "README.md")
    sources = discover_sources(cfg, repo_root=repo)
    kinds = {s.kind for s in sources}
    assert "readme" in kinds
    assert "tests" in kinds
    assert "ci" in kinds


def test_extract_insights_reads_journal_events(tmp_path):
    journal = tmp_path / "j.jsonl"
    journal.write_text(
        json.dumps({"event": "risk.review", "proposals": [
            {"symbol": "AAPL", "approved": False, "risk_notes": ["LLM veto: crowded"]}
        ]}) + "\n",
        encoding="utf-8",
    )
    extracted = extract_insights(
        [],
        journal_path=journal,
        plasticity_path=tmp_path / "missing.json",
    )
    assert extracted["recent_vetoes"]
    assert extracted["recent_vetoes"][0]["symbol"] == "AAPL"


def test_write_adaptations_persists_learnings(tmp_path):
    store = WorkloopStore(tmp_path / "workloop")
    extracted = {
        "source_kinds": ["journal", "tests"],
        "journal_events": {"broker.error": 3},
        "recent_vetoes": [{"symbol": "NVDA", "note": "LLM veto: size"}],
        "plasticity_lessons": [],
        "git_commits": ["abc123 init"],
    }
    adaptations = write_adaptations(store, extracted, max_lessons=5)
    learnings = store.load_learnings()
    assert adaptations
    assert learnings["lessons"]
    assert learnings["adaptations"]


def test_approval_gate_requires_aaron(tmp_path):
    store = WorkloopStore(tmp_path / "workloop")
    with pytest.raises(ApprovalRequired):
        check_approval(store, run_id="run-1", approver="Aaron")

    record_approval(store, run_id="run-1", approver="Aaron", note="LGTM")
    approval = check_approval(store, run_id="run-1", approver="Aaron")
    assert approval["approver"] == "Aaron"


def test_workloop_halts_at_approval_without_signoff(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    orch = WorkloopOrchestrator(cfg, repo_root=Path(__file__).resolve().parents[1])

    monkeypatch.setattr("aoa.workloop.stages.run_verify", lambda _root: {"passed": True})
    monkeypatch.setattr("aoa.workloop.stages.run_upgrade", lambda _root: {"ok": True})

    result = orch.run(dry_run=False)
    assert result.halted is True
    assert result.run.status == "awaiting_approval"
    assert result.run.stage == "approval"


def test_workloop_resumes_after_aaron_approves(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    orch = WorkloopOrchestrator(cfg, repo_root=Path(__file__).resolve().parents[1])

    monkeypatch.setattr("aoa.workloop.stages.run_verify", lambda _root: {"passed": True})
    monkeypatch.setattr("aoa.workloop.stages.run_upgrade", lambda _root: {"ok": True})
    monkeypatch.setattr(
        "aoa.workloop.stages.run_merge",
        lambda proposal, **kwargs: {"message": "merge skipped"},
    )

    halted = orch.run(dry_run=False)
    assert halted.halted is True

    orch.approve(approver="Aaron", note="ship it")
    completed = orch.run(resume=True, from_stage="approval")
    assert completed.halted is False
    assert completed.run.status == "completed"
    assert completed.run.verify.get("passed") is True
    assert completed.run.reverify.get("passed") is True


def test_workloop_dry_run_completes_without_approval(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    orch = WorkloopOrchestrator(cfg, repo_root=Path(__file__).resolve().parents[1])
    monkeypatch.setattr("aoa.workloop.stages.run_verify", lambda _root: {"passed": True})

    result = orch.run(dry_run=True)
    assert result.halted is False
    assert result.run.status == "completed"
    events = {e["event"] for e in orch.store.tail(30)}
    assert "workloop.complete" in events


def test_build_proposal_reports_git_state():
    repo = Path(__file__).resolve().parents[1]
    proposal = build_proposal(repo)
    assert "branch" in proposal
    assert "changed_files" in proposal
    assert "summary" in proposal
