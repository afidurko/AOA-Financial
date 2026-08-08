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
from aoa.workloop.scheduler import WorkloopScheduler
from aoa.workloop.stages import default_stages
from aoa.workloop.store import WorkloopStore


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


def test_default_workloop_has_twelve_stages():
    names = [s.name for s in default_stages()]
    assert names == list(STAGE_ORDER)
    assert "team_review" in names


def _stub_team_review(monkeypatch, *, verdict="approve", required_approver="Aaron"):
    def _fake(**kwargs):
        return {
            "run_id": kwargs.get("run_id", ""),
            "verdict": verdict,
            "required_approver": required_approver,
            "summary": f"stub team review ({verdict})",
            "escalation_messages": [],
            "bob": {"can_proceed": True},
            "julie": {"status": "ok"},
            "alan": {"recommendation": verdict},
            "aaron": {"verdict": verdict, "required_approver": required_approver},
        }

    monkeypatch.setattr("aoa.workloop.stages.review_change_proposal", _fake)


def _stub_pending_changes(monkeypatch):
    monkeypatch.setattr(
        "aoa.workloop.stages.build_proposal",
        lambda _root: {
            "branch": "main",
            "changed_files": ["src/aoa/cli.py"],
            "has_changes": True,
            "summary": "1 file(s) changed on main: src/aoa/cli.py",
            "status_porcelain": " M src/aoa/cli.py",
            "diff_stat": " src/aoa/cli.py | 1 +\n",
        },
    )


def test_discover_sources_finds_core_materials(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    cfg = _config(tmp_path, journal_path=repo / "README.md")
    sources = discover_sources(cfg, repo_root=repo)
    kinds = {s.kind for s in sources}
    assert "readme" in kinds
    assert "tests" in kinds
    assert "ci" in kinds
    assert "loop_state" in kinds
    assert "loop_config" in kinds
    assert "loop_constraints" in kinds
    assert "loop_run_log" in kinds


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

    _stub_team_review(monkeypatch)
    _stub_pending_changes(monkeypatch)
    monkeypatch.setattr("aoa.workloop.stages.run_verify", lambda _root: {"passed": True})
    monkeypatch.setattr("aoa.workloop.stages.run_upgrade", lambda _root: {"ok": True})

    result = orch.run(dry_run=False)
    assert result.halted is True
    assert result.run.status == "awaiting_approval"
    assert result.run.stage == "approval"
    assert result.run.team_review.get("verdict") == "approve"


def test_workloop_resumes_after_aaron_approves(tmp_path, monkeypatch):
    cfg = _config(tmp_path)
    orch = WorkloopOrchestrator(cfg, repo_root=Path(__file__).resolve().parents[1])

    _stub_team_review(monkeypatch)
    _stub_pending_changes(monkeypatch)
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


def test_scheduler_chains_completed_runs(tmp_path, monkeypatch):
    cfg = _config(tmp_path, workloop_interval_seconds=60)
    repo = Path(__file__).resolve().parents[1]
    orch = WorkloopOrchestrator(cfg, repo_root=repo)
    scheduler = WorkloopScheduler(orch, interval_seconds=60, sleep_fn=lambda _s: None)

    monkeypatch.setattr("aoa.workloop.stages.run_verify", lambda _root: {"passed": True})

    first = scheduler.tick(dry_run=True)
    assert first.action == "completed"
    assert first.result.run.status == "completed"

    sched = scheduler.state()
    assert sched.iteration == 1
    assert sched.last_completed_run_id == first.result.run.run_id
    assert sched.next_run_at
    assert orch.store.load_run() is None

    second = scheduler.tick(dry_run=True)
    assert second.action == "completed"
    assert second.result.run.iteration == 2
    assert second.result.run.previous_run_id == first.result.run.run_id
    assert "Chained iteration" in " ".join(second.result.run.notes)


def test_scheduler_polls_approval_then_resumes(tmp_path, monkeypatch):
    cfg = _config(tmp_path, workloop_interval_seconds=60)
    repo = Path(__file__).resolve().parents[1]
    orch = WorkloopOrchestrator(cfg, repo_root=repo)
    scheduler = WorkloopScheduler(orch, interval_seconds=60, sleep_fn=lambda _s: None)

    _stub_team_review(monkeypatch)
    _stub_pending_changes(monkeypatch)
    monkeypatch.setattr("aoa.workloop.stages.run_verify", lambda _root: {"passed": True})
    monkeypatch.setattr("aoa.workloop.stages.run_upgrade", lambda _root: {"ok": True})
    monkeypatch.setattr(
        "aoa.workloop.stages.run_merge",
        lambda proposal, **kwargs: {"message": "merge skipped"},
    )

    halted = scheduler.tick(dry_run=False)
    assert halted.action == "awaiting_approval"

    still_waiting = scheduler.tick(dry_run=False)
    assert still_waiting.action == "awaiting_approval"

    orch.approve(approver="Aaron")
    resumed = scheduler.tick(dry_run=False)
    assert resumed.action == "resumed"
    assert resumed.result.run.status == "completed"
    assert scheduler.state().iteration == 1


def test_extract_includes_prior_workloop_learnings(tmp_path):
    store = WorkloopStore(tmp_path / "workloop")
    store.save_learnings({"lessons": ["avoid repeat vetoes on AAPL"], "adaptations": []})
    store.save_scheduler({"iteration": 2, "last_completed_run_id": "abc", "status": "sleeping"})

    extracted = extract_insights(
        [],
        journal_path=tmp_path / "missing.jsonl",
        plasticity_path=tmp_path / "missing.json",
        workloop_path=tmp_path / "workloop",
        previous_run_id="abc",
    )
    assert "avoid repeat vetoes on AAPL" in extracted["workloop_lessons"]
    assert extracted["prior_iterations"] == 2
    assert extracted["previous_run_id"] == "abc"


def test_team_review_rejects_when_bob_blocks(tmp_path, monkeypatch):
    from aoa.team.code_engineering import CodeFinding, CodeQualityReport, HealthStatus
    from aoa.workloop import team_review as tr_mod

    monkeypatch.setattr(
        tr_mod,
        "run_code_quality_audit",
        lambda **kwargs: CodeQualityReport(
            findings=[CodeFinding("ruff", HealthStatus.CRITICAL, "broken")],
            can_proceed=False,
            summary="critical",
        ),
    )
    review = tr_mod.review_change_proposal(
        proposal={"has_changes": True, "changed_files": ["src/aoa/cli.py"], "summary": "cli"},
        adaptations=[],
        repo_root=Path(__file__).resolve().parents[1],
        config=_config(tmp_path),
        run_id="run-test",
        llm=None,
    )
    assert review["verdict"] == "reject"


def test_team_review_escalates_sensitive_paths(tmp_path, monkeypatch):
    from aoa.team.code_engineering import CodeQualityReport
    from aoa.workloop import team_review as tr_mod

    monkeypatch.setattr(
        tr_mod,
        "run_code_quality_audit",
        lambda **kwargs: CodeQualityReport(can_proceed=True, summary="ok"),
    )
    review = tr_mod.review_change_proposal(
        proposal={
            "has_changes": True,
            "changed_files": [".env.production"],
            "summary": "secrets",
        },
        adaptations=[],
        repo_root=Path(__file__).resolve().parents[1],
        config=_config(tmp_path),
        run_id="run-sensitive",
        llm=None,
    )
    assert review["verdict"] == "escalate_user"
    assert review["required_approver"] == "user"


def test_workloop_escalated_changes_require_user_approval(tmp_path, monkeypatch):
    cfg = _config(tmp_path, workloop_user_approver="user")
    orch = WorkloopOrchestrator(cfg, repo_root=Path(__file__).resolve().parents[1])
    _stub_team_review(monkeypatch, verdict="escalate_user", required_approver="user")
    _stub_pending_changes(monkeypatch)
    monkeypatch.setattr("aoa.workloop.stages.run_verify", lambda _root: {"passed": True})
    monkeypatch.setattr("aoa.workloop.stages.run_upgrade", lambda _root: {"ok": True})
    monkeypatch.setattr(
        "aoa.workloop.stages.run_merge",
        lambda proposal, **kwargs: {"message": "merge skipped"},
    )

    halted = orch.run(dry_run=False)
    assert halted.halted is True
    assert halted.run.team_review["required_approver"] == "user"

    orch.approve(approver="Aaron", note="wrong approver")
    still = orch.run(resume=True, from_stage="approval")
    assert still.halted is True

    orch.approve(approver="user", note="confirmed")
    done = orch.run(resume=True, from_stage="approval")
    assert done.halted is False
    assert done.run.status == "completed"

