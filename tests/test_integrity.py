"""Tests for Integrity Ten — cohesive integrity mesh."""

from __future__ import annotations

import json
from pathlib import Path

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
