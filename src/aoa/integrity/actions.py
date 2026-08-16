"""Corrective actions — propose fixes and gate implant on user approval.

Policy (loop-constraints hard floor):
- Never auto-merge; draft / suggest only until the user approves.
- Never touch .env, secrets, profiles/live.env, or risk/guards.py.
- Aaron notifies; Alex routes approval BRIEF; Reed queues the implant.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.integrity.checks import DomainReport, IntegrityFinding, IntegritySeverity


@dataclass
class CorrectiveProposal:
    """One proposed corrective action awaiting user implant decision."""

    id: str
    title: str
    summary: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    automatable: bool = False
    status: str = "pending"  # pending | approved | rejected | applied
    created_at: str = ""
    resolved_at: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "findings": list(self.findings),
            "automatable": self.automatable,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorrectiveProposal:
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            summary=str(data.get("summary") or ""),
            findings=list(data.get("findings") or []),
            automatable=bool(data.get("automatable")),
            status=str(data.get("status") or "pending"),
            created_at=str(data.get("created_at") or ""),
            resolved_at=str(data.get("resolved_at") or ""),
            note=str(data.get("note") or ""),
        )


def default_queue_path(repo_root: Path, data_dir: Path | None = None) -> Path:
    base = data_dir or (repo_root / "data" / "paper" / "integrity")
    return base / "corrective_queue.json"


def load_queue(path: Path) -> list[CorrectiveProposal]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [CorrectiveProposal.from_dict(x) for x in items if isinstance(x, dict)]


def save_queue(path: Path, proposals: list[CorrectiveProposal]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": [p.to_dict() for p in proposals],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def findings_needing_action(
    reports: list[DomainReport],
) -> list[IntegrityFinding]:
    out: list[IntegrityFinding] = []
    for report in reports:
        for finding in report.findings:
            if finding.status is IntegritySeverity.OK:
                continue
            out.append(finding)
    return out


def propose_from_reports(
    reports: list[DomainReport],
    *,
    queue_path: Path,
) -> CorrectiveProposal | None:
    """Create one pending proposal from non-OK findings (deduped by title)."""
    bad = findings_needing_action(reports)
    if not bad:
        return None

    critical = [f for f in bad if f.status is IntegritySeverity.CRITICAL]
    focus = critical or bad
    automatable = all(f.automatable for f in focus)
    title = (
        f"Integrity corrective action ({len(focus)} finding"
        f"{'s' if len(focus) != 1 else ''})"
    )
    lines = [f"- [{f.agent}/{f.domain}] {f.detail}" for f in focus[:12]]
    summary = "\n".join(lines)
    if len(focus) > 12:
        summary += f"\n… and {len(focus) - 12} more"

    existing = load_queue(queue_path)
    # Dedupe: if an identical pending summary exists, return it.
    for prop in existing:
        if prop.status == "pending" and prop.summary == summary:
            return prop

    prop = CorrectiveProposal(
        id=f"int-{uuid.uuid4().hex[:10]}",
        title=title,
        summary=summary,
        findings=[f.to_dict() for f in focus],
        automatable=automatable,
        status="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    existing.append(prop)
    save_queue(queue_path, existing)
    return prop


def get_proposal(queue_path: Path, proposal_id: str) -> CorrectiveProposal | None:
    for prop in load_queue(queue_path):
        if prop.id == proposal_id:
            return prop
    return None


def resolve_proposal(
    queue_path: Path,
    proposal_id: str,
    *,
    status: str,
    note: str = "",
) -> CorrectiveProposal:
    if status not in {"approved", "rejected", "applied"}:
        raise ValueError(f"Invalid status {status!r}")
    items = load_queue(queue_path)
    found: CorrectiveProposal | None = None
    for prop in items:
        if prop.id == proposal_id:
            if prop.status not in {"pending", "approved"}:
                raise ValueError(
                    f"Proposal {proposal_id} is {prop.status}; cannot set {status}."
                )
            prop.status = status
            prop.note = note
            prop.resolved_at = datetime.now(timezone.utc).isoformat()
            found = prop
            break
    if found is None:
        raise KeyError(f"No proposal with id {proposal_id}")
    save_queue(queue_path, items)
    return found


def apply_safe_fixes(
    proposal: CorrectiveProposal,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Apply only safe, non-code-mutating integrity repairs after user approval.

    Safe implants today:
    - ensure brain workspace skeleton
    - Nova capture documenting the approved corrective action

    Code mutations still go through Reed → repair worktree → draft PR (never merge).
    """
    from aoa.brain.store import BrainStore, ensure_brain_workspace

    ensure_brain_workspace(repo_root)
    store = BrainStore.open(repo_root)
    capture = store.write_capture(
        f"Integrity implant {proposal.id}",
        (
            f"User approved corrective action `{proposal.id}`.\n\n"
            f"{proposal.summary}\n\n"
            f"Note: {proposal.note or '(none)'}\n\n"
            "Reed may open a draft PR for code findings; hard floor still applies."
        ),
    )
    # Queue a repair-style note for Reed when findings look code-related.
    codeish = [
        f
        for f in proposal.findings
        if str(f.get("domain")) in {"code", "algorithms"}
        or str(f.get("status")) == "critical"
    ]
    repair_queued = False
    if codeish:
        repair_queued = _append_repair_hint(repo_root, proposal)

    return {
        "proposal_id": proposal.id,
        "capture": str(capture),
        "brain_ensured": True,
        "repair_hint_queued": repair_queued,
        "draft_pr_only": True,
        "auto_merged": False,
    }


def _append_repair_hint(repo_root: Path, proposal: CorrectiveProposal) -> bool:
    """Append a human-visible repair note under data/.../integrity for Reed."""
    path = repo_root / "data" / "paper" / "integrity" / "reed_handoff.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "proposal_id": proposal.id,
        "title": proposal.title,
        "findings": proposal.findings,
        "instruction": "Draft PR only after maker+verifier; never auto-merge.",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return True


def build_user_notification(proposal: CorrectiveProposal) -> dict[str, Any]:
    """Payload for Aaron → user: action proposed; implant only if user approves."""
    return {
        "kind": "approval",
        "title": proposal.title,
        "message": (
            "Integrity Ten found issues and prepared a corrective action. "
            "Approve to implant (safe repairs + Reed draft-PR handoff), "
            "or reject to leave the queue untouched.\n\n"
            f"{proposal.summary}\n\n"
            f"Respond: aoa integrity approve {proposal.id}\n"
            f"Or:       aoa integrity reject {proposal.id}"
        ),
        "requires_response": True,
        "priority": "high" if any(
            f.get("status") == "critical" for f in proposal.findings
        ) else "normal",
        "proposal_id": proposal.id,
        "automatable": proposal.automatable,
    }
