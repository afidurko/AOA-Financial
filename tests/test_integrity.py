"""Tests for Integrity Ten — cohesive integrity mesh."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa.cli import main
from aoa.integrity.actions import (
    apply_safe_fixes,
    propose_from_reports,
    resolve_proposal,
)
from aoa.integrity.checks import (
    DomainReport,
    IntegrityFinding,
    IntegritySeverity,
    check_cohesion,
    run_all_checks,
)
from aoa.integrity.roster import INTEGRITY_TEN, integrity_names
from aoa.integrity.squad import IntegritySquad
from aoa.team.roster import roster_names


def test_integrity_ten_unique_subset_of_twelve():
    names = integrity_names()
    assert len(INTEGRITY_TEN) == 10
    assert len(set(names)) == 10
    twelve = set(roster_names())
    assert set(names) <= twelve
    assert "Tom" not in names
    assert "Morgan" not in names
    assert {"Bob", "Nova", "Reed", "Kai", "Aaron", "Alex"} <= set(names)


def test_cohesion_check_ok_on_repo():
    report = check_cohesion(Path.cwd())
    assert report.status is IntegritySeverity.OK
    assert report.agent == "Alan"


def test_run_all_checks_shape():
    reports = run_all_checks(Path.cwd())
    domains = {r.domain for r in reports}
    assert {
        "code",
        "algorithms",
        "docs",
        "safety",
        "neural_memory",
        "workspaces",
        "cohesion",
    } <= domains
    for report in reports:
        assert report.findings
        assert report.agent


def test_propose_approve_reject_flow(tmp_path: Path):
    queue = tmp_path / "corrective_queue.json"
    reports = [
        DomainReport(
            domain="code",
            agent="Bob",
            status=IntegritySeverity.DEGRADED,
            findings=[
                IntegrityFinding(
                    domain="code",
                    agent="Bob",
                    status=IntegritySeverity.DEGRADED,
                    detail="lint drift",
                    automatable=True,
                    fix_hint="ruff",
                )
            ],
            summary="degraded",
        )
    ]
    prop = propose_from_reports(reports, queue_path=queue)
    assert prop is not None
    assert prop.status == "pending"

    # Dedupes identical pending proposal
    again = propose_from_reports(reports, queue_path=queue)
    assert again is not None
    assert again.id == prop.id

    rejected = resolve_proposal(queue, prop.id, status="rejected", note="later")
    assert rejected.status == "rejected"

    # New proposal after reject
    prop2 = propose_from_reports(reports, queue_path=queue)
    assert prop2 is not None
    assert prop2.id != prop.id


def test_squad_dry_run_and_approve_implant(tmp_path: Path):
    _seed_minimal_repo(tmp_path)
    squad = IntegritySquad(repo_root=tmp_path, data_dir=tmp_path / "data" / "integrity")
    dry = squad.run(dry_run=True, notify=False)
    assert dry.outcome in {"healthy", "issues-dry-run"}
    assert dry.roster == integrity_names()

    # Force a proposal via fake degraded report path: mutate by writing bad mesh members
    mesh = tmp_path / "brain" / "mesh" / "index.yaml"
    mesh.write_text("mode: auto-12\nmembers: []\nalgorithms: []\n", encoding="utf-8")
    live = squad.run(dry_run=False, notify=False)
    assert live.outcome in {"awaiting_user", "issues-no-proposal", "healthy"}
    if live.proposal:
        pid = live.proposal["id"]
        result = squad.approve(pid, note="implant")
        assert result["proposal"]["status"] == "applied"
        assert result["applied"]["auto_merged"] is False
        assert Path(result["applied"]["capture"]).is_file()


def test_apply_safe_fixes_writes_capture(tmp_path: Path):
    _seed_minimal_repo(tmp_path)
    from aoa.integrity.actions import CorrectiveProposal

    prop = CorrectiveProposal(
        id="int-test",
        title="test",
        summary="- finding",
        findings=[{"domain": "code", "status": "degraded"}],
        status="approved",
    )
    out = apply_safe_fixes(prop, repo_root=tmp_path)
    assert out["brain_ensured"] is True
    assert Path(out["capture"]).is_file()
    assert out["draft_pr_only"] is True


def test_cli_integrity_roster_and_status(capsys):
    assert main(["integrity", "roster"]) == 0
    out = capsys.readouterr().out
    assert "Integrity Ten" in out
    assert "Bob" in out
    assert main(["integrity", "status", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["roster_size"] == 10
    assert data["unit"] == "integrity-ten"


def test_cli_integrity_run_dry(capsys):
    assert main(["integrity", "run", "--dry-run", "--no-notify"]) == 0
    out = capsys.readouterr().out
    assert "Integrity Ten" in out
    assert "outcome:" in out


def test_queue_notify_digest_and_push(tmp_path: Path, monkeypatch):
    from aoa.integrity.actions import propose_from_reports
    from aoa.notify.iphone import IPhoneNotifier

    queue = tmp_path / "corrective_queue.json"
    reports = [
        DomainReport(
            domain="code",
            agent="Bob",
            status=IntegritySeverity.DEGRADED,
            findings=[
                IntegrityFinding(
                    domain="code",
                    agent="Bob",
                    status=IntegritySeverity.DEGRADED,
                    detail="queue notify demo",
                    automatable=True,
                )
            ],
            summary="degraded",
        )
    ]
    prop = propose_from_reports(reports, queue_path=queue)
    assert prop is not None

    sent: list[str] = []

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        sent.append(url)
        return FakeResp()

    monkeypatch.setattr("aoa.notify.iphone.httpx.post", fake_post)
    squad = IntegritySquad(
        repo_root=tmp_path,
        data_dir=tmp_path,
        notifier=IPhoneNotifier(ntfy_topic="aoa-integrity-test"),
    )
    # Point queue at our temp file
    squad.queue_path = queue
    result = squad.notify_queue(digest=True)
    assert result["pending"] == 1
    assert result["pushed"] is True
    assert "ntfy" in result["channels"]
    assert sent and sent[0].endswith("/aoa-integrity-test")


def test_cli_integrity_queue(capsys):
    assert main(["integrity", "queue", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "pending" in data
    assert "notify" in data


def test_cursor_attention_payload(tmp_path: Path):
    from aoa.integrity.actions import propose_from_reports
    from aoa.integrity.attention import cursor_mcp_payload, write_cursor_attention_file

    queue = tmp_path / "corrective_queue.json"
    reports = [
        DomainReport(
            domain="code",
            agent="Bob",
            status=IntegritySeverity.DEGRADED,
            findings=[
                IntegrityFinding(
                    domain="code",
                    agent="Bob",
                    status=IntegritySeverity.DEGRADED,
                    detail="needs attention demo",
                    automatable=True,
                )
            ],
            summary="degraded",
        )
    ]
    prop = propose_from_reports(reports, queue_path=queue)
    assert prop is not None
    payload = cursor_mcp_payload(queue)
    assert payload["pending"] == 1
    assert payload["mcp_tool"] == "request-environment-setup-actions"
    assert any(a["type"] == "external_action" for a in payload["actions"])
    assert any(prop.id in a["id"] for a in payload["actions"])
    path = write_cursor_attention_file(queue)
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["pending"] == 1


def test_corrupt_queue_fails_closed(tmp_path: Path):
    from aoa.integrity.actions import QueueCorruptError, load_queue, propose_from_reports

    queue = tmp_path / "corrective_queue.json"
    queue.write_text("{not-json", encoding="utf-8")
    with pytest.raises(QueueCorruptError):
        load_queue(queue)
    reports = [
        DomainReport(
            domain="code",
            agent="Bob",
            status=IntegritySeverity.DEGRADED,
            findings=[
                IntegrityFinding(
                    domain="code",
                    agent="Bob",
                    status=IntegritySeverity.DEGRADED,
                    detail="x",
                )
            ],
            summary="x",
        )
    ]
    with pytest.raises(QueueCorruptError):
        propose_from_reports(reports, queue_path=queue)
    # Corrupt file must remain untouched
    assert queue.read_text(encoding="utf-8") == "{not-json"


def test_empty_queue_file_fails_closed(tmp_path: Path):
    from aoa.integrity.actions import QueueCorruptError, load_queue

    queue = tmp_path / "corrective_queue.json"
    queue.write_text("   \n", encoding="utf-8")
    with pytest.raises(QueueCorruptError, match="Empty"):
        load_queue(queue)


def test_digest_sync_keeps_alert_until_all_resolved(tmp_path: Path):
    from aoa.analytics.store import AnalyticsStore
    from aoa.integrity.actions import CorrectiveProposal, save_queue

    _seed_minimal_repo(tmp_path)
    queue = tmp_path / "data" / "integrity" / "corrective_queue.json"
    queue.parent.mkdir(parents=True, exist_ok=True)
    a = CorrectiveProposal(
        id="int-a", title="A", summary="a", status="pending", created_at="t"
    )
    b = CorrectiveProposal(
        id="int-b", title="B", summary="b", status="pending", created_at="t"
    )
    save_queue(queue, [a, b])

    store = AnalyticsStore(tmp_path / "analytics.sqlite")
    nid = store.log_notification(
        kind="approval",
        title="digest",
        message="approve?",
        payload={"proposal_ids": ["int-a", "int-b"]},
    )
    store.mark_awaiting_response(nid)

    squad = IntegritySquad(repo_root=tmp_path, data_dir=queue.parent)
    squad.queue_path = queue
    squad.analytics_store = store
    squad.approve("int-a", note="one")
    pending = store.list_pending_responses()
    assert [p["id"] for p in pending] == [nid]
    squad.approve("int-b", note="two")
    assert store.list_pending_responses() == []
    store.close()


def test_legacy_approved_can_finish_implant(tmp_path: Path):
    from aoa.integrity.actions import CorrectiveProposal, get_proposal, save_queue

    _seed_minimal_repo(tmp_path)
    queue = tmp_path / "data" / "integrity" / "corrective_queue.json"
    queue.parent.mkdir(parents=True, exist_ok=True)
    prop = CorrectiveProposal(
        id="int-stuck",
        title="stuck",
        summary="legacy approved",
        findings=[{"domain": "code", "status": "degraded"}],
        status="approved",
        created_at="t",
    )
    save_queue(queue, [prop])
    squad = IntegritySquad(repo_root=tmp_path, data_dir=queue.parent)
    squad.queue_path = queue
    out = squad.approve("int-stuck", note="finish")
    assert out["proposal"]["status"] == "applied"
    assert get_proposal(queue, "int-stuck").status == "applied"


def test_corrupt_plasticity_is_degraded(tmp_path: Path):
    from aoa.integrity.checks import check_neural_memory

    _seed_minimal_repo(tmp_path)
    plastic = tmp_path / "data" / "paper-dry" / "journal" / "plasticity.json"
    plastic.parent.mkdir(parents=True, exist_ok=True)
    plastic.write_text("{not-json", encoding="utf-8")
    report = check_neural_memory(tmp_path)
    assert any(
        f.status is IntegritySeverity.DEGRADED and "Corrupt plasticity" in f.detail
        for f in report.findings
    )


def test_approve_refreshes_cursor_attention(tmp_path: Path):
    from aoa.integrity.actions import propose_from_reports
    from aoa.integrity.attention import cursor_mcp_payload

    _seed_minimal_repo(tmp_path)
    queue = tmp_path / "data" / "integrity" / "corrective_queue.json"
    queue.parent.mkdir(parents=True, exist_ok=True)
    reports = [
        DomainReport(
            domain="code",
            agent="Bob",
            status=IntegritySeverity.DEGRADED,
            findings=[
                IntegrityFinding(
                    domain="code",
                    agent="Bob",
                    status=IntegritySeverity.DEGRADED,
                    detail="attention refresh",
                    automatable=True,
                )
            ],
            summary="attn",
        )
    ]
    prop = propose_from_reports(reports, queue_path=queue)
    assert prop is not None
    squad = IntegritySquad(repo_root=tmp_path, data_dir=tmp_path / "data" / "integrity")
    squad.queue_path = queue
    before = cursor_mcp_payload(queue)
    assert before["pending"] == 1
    squad.approve(prop.id, note="test")
    after = cursor_mcp_payload(queue)
    assert after["pending"] == 0
    attention = queue.parent / "cursor_needs_attention.json"
    assert attention.is_file()
    saved = json.loads(attention.read_text(encoding="utf-8"))
    assert saved["pending"] == 0


def test_reed_handoff_uses_queue_dir(tmp_path: Path):
    from aoa.integrity.actions import CorrectiveProposal, apply_safe_fixes

    _seed_minimal_repo(tmp_path)
    handoff = tmp_path / "data" / "paper-dry" / "integrity"
    prop = CorrectiveProposal(
        id="int-handoff",
        title="t",
        summary="s",
        findings=[{"domain": "code", "status": "degraded"}],
        status="pending",
    )
    out = apply_safe_fixes(prop, repo_root=tmp_path, handoff_dir=handoff)
    assert out["repair_hint_queued"] is True
    assert (handoff / "reed_handoff.jsonl").is_file()
    assert not (tmp_path / "data" / "paper" / "integrity" / "reed_handoff.jsonl").exists()


def test_cli_integrity_attention_cursor(capsys, tmp_path, monkeypatch):
    # Use real queue path under cwd data — just ensure CLI emits JSON shape
    assert main(["integrity", "attention", "--cursor"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mcp_tool"] == "request-environment-setup-actions"
    assert "actions" in data


def _seed_minimal_repo(root: Path) -> None:
    (root / "STATE.md").write_text("## Loop automation\n\n- L1: enabled\n", encoding="utf-8")
    (root / "loop-constraints.md").write_text(
        Path.cwd().joinpath("loop-constraints.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "docs" / "design").mkdir(parents=True)
    (root / "docs" / "design" / "agentic-task-team-loop.md").write_text(
        "# ATTL\n", encoding="utf-8"
    )
    (root / "docs" / "safety.md").write_text("# safety\n", encoding="utf-8")
    (root / "src" / "aoa" / "risk").mkdir(parents=True)
    (root / "src" / "aoa" / "risk" / "guards.py").write_text(
        "def guard():\n    return True\n", encoding="utf-8"
    )
    # Minimal brain
    for rel in (
        "brain/_CLAUDE.md",
        "brain/README.md",
        "brain/spine/ATTL.md",
        "brain/spine/Algorithms.md",
        "brain/spine/Team-Mesh.md",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.name}\n", encoding="utf-8")
    (root / "brain" / "captures").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "decisions").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "mesh").mkdir(parents=True, exist_ok=True)
    members = "\n".join(
        f"  - id: {n.lower()}\n    name: {n}\n    role: x\n    feeds: []"
        for n in roster_names()
    )
    (root / "brain" / "mesh" / "index.yaml").write_text(
        f"mode: auto-12\nmembers:\n{members}\nalgorithms: []\nspines: []\n",
        encoding="utf-8",
    )
    (root / "brain" / "mesh" / "repos.yaml").write_text("repos: []\n", encoding="utf-8")
    # Code quality audit needs a few src modules — point checks at cwd for
    # pricing etc. Squad cohesion uses INTEGRITY_TEN constant (repo), not tmp.
    # Copy pyproject marker so code audit can find repo root if needed.
    (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
    (root / "src" / "aoa").mkdir(parents=True, exist_ok=True)
