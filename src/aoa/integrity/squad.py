"""Integrity Ten squad — cohesive continuous integrity mesh."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.brain.store import BrainStore
from aoa.constraints import load_constraints
from aoa.integrity.actions import (
    CorrectiveProposal,
    apply_safe_fixes,
    build_user_notification,
    default_queue_path,
    load_queue,
    propose_from_reports,
    resolve_proposal,
)
from aoa.integrity.checks import (
    DomainReport,
    IntegritySeverity,
    run_all_checks,
)
from aoa.integrity.roster import INTEGRITY_TEN, integrity_names
from aoa.team.kai import KaiAgent


@dataclass
class IntegrityCycleResult:
    """Outcome of one Integrity Ten cycle."""

    ok: bool
    outcome: str
    roster: list[str] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)
    worst_status: str = "ok"
    proposal: dict[str, Any] | None = None
    notification: dict[str, Any] | None = None
    kai: dict[str, Any] = field(default_factory=dict)
    capture: str = ""
    notes: list[str] = field(default_factory=list)
    paused: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "outcome": self.outcome,
            "roster": list(self.roster),
            "reports": list(self.reports),
            "worst_status": self.worst_status,
            "proposal": self.proposal,
            "notification": self.notification,
            "kai": self.kai,
            "capture": self.capture,
            "notes": list(self.notes),
            "paused": self.paused,
        }


class IntegritySquad:
    """Ten-agent cohesive unit for continuous integrity monitoring."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        data_dir: Path | None = None,
        llm=None,
        notifier: Any | None = None,
        analytics_store: Any | None = None,
    ) -> None:
        self.repo_root = repo_root or Path.cwd()
        self.data_dir = data_dir or (self.repo_root / "data" / "paper" / "integrity")
        self.queue_path = default_queue_path(self.repo_root, self.data_dir)
        self.kai = KaiAgent(llm or _NullLLM())
        self.notifier = notifier
        self.analytics_store = analytics_store

    def roster(self) -> list[dict[str, str]]:
        return [
            {
                "name": m.name,
                "role": m.role,
                "slug": m.slug,
                "domain": m.domain,
            }
            for m in INTEGRITY_TEN
        ]

    def status(self) -> dict[str, Any]:
        cs = load_constraints(self.repo_root)
        pending = [p.to_dict() for p in load_queue(self.queue_path) if p.status == "pending"]
        brain = BrainStore.open(self.repo_root).stats()
        return {
            "unit": "integrity-ten",
            "roster_size": len(INTEGRITY_TEN),
            "roster": integrity_names(),
            "paused": cs.pause_active,
            "mode": cs.mode,
            "pending_proposals": len(pending),
            "proposals": pending,
            "brain": brain,
            "queue_path": str(self.queue_path),
        }

    def run(self, *, dry_run: bool = False, notify: bool = True) -> IntegrityCycleResult:
        """One cohesive cycle: check → propose → notify (implant only after approve)."""
        notes: list[str] = []
        cs = load_constraints(self.repo_root)
        if cs.pause_active:
            return IntegrityCycleResult(
                ok=False,
                outcome="paused",
                roster=integrity_names(),
                paused=True,
                notes=["Hard floor: loop-pause-all active — Integrity Ten halted."],
            )

        reports = run_all_checks(self.repo_root)
        report_dicts = [r.to_dict() for r in reports]
        worst = _worst_status(reports)
        notes.append(f"Integrity Ten completed {len(reports)} domain checks.")

        critical = worst is IntegritySeverity.CRITICAL
        kai = self.kai.review_if_needed(
            {
                "needs_review": critical,
                "critical": critical,
                "reason": "integrity_critical" if critical else "none",
                "summary": _summarize(reports),
            }
        )
        notes.append(
            "Kai engaged." if kai.get("engaged") else "Kai skipped (non-critical)."
        )

        proposal: CorrectiveProposal | None = None
        notification: dict[str, Any] | None = None
        if worst is not IntegritySeverity.OK:
            if dry_run:
                notes.append("Dry-run: corrective proposal not written.")
                outcome = "issues-dry-run"
            else:
                proposal = propose_from_reports(reports, queue_path=self.queue_path)
                if proposal:
                    notification = build_user_notification(proposal)
                    notes.append(
                        f"Aaron prepared proposal {proposal.id}; "
                        "implant waits on user approve/reject."
                    )
                    if notify:
                        self._dispatch_notification(notification, proposal)
                    outcome = "awaiting_user"
                else:
                    outcome = "issues-no-proposal"
        else:
            outcome = "healthy"

        capture = ""
        if not dry_run:
            body = (
                f"Outcome: {outcome}\nWorst: {worst.value}\n\n"
                f"Notes:\n" + "\n".join(f"- {n}" for n in notes)
            )
            if proposal:
                body += f"\n\nProposal: `{proposal.id}`\n{proposal.summary}"
            path = BrainStore.open(self.repo_root).write_capture(
                "Integrity Ten cycle",
                body,
                critical=critical,
            )
            capture = str(path)

        return IntegrityCycleResult(
            ok=worst is IntegritySeverity.OK,
            outcome=outcome,
            roster=integrity_names(),
            reports=report_dicts,
            worst_status=worst.value,
            proposal=proposal.to_dict() if proposal else None,
            notification=notification,
            kai=kai,
            capture=capture,
            notes=notes,
            paused=False,
        )

    def watch(
        self,
        *,
        interval_seconds: int = 300,
        iterations: int | None = None,
        dry_run: bool = False,
        notify: bool = True,
    ) -> list[IntegrityCycleResult]:
        """Continuously run integrity cycles until iterations exhausted or pause."""
        results: list[IntegrityCycleResult] = []
        n = 0
        while iterations is None or n < iterations:
            result = self.run(dry_run=dry_run, notify=notify)
            results.append(result)
            n += 1
            if result.paused:
                break
            if iterations is not None and n >= iterations:
                break
            time.sleep(max(1, int(interval_seconds)))
        return results

    def approve(self, proposal_id: str, *, note: str = "") -> dict[str, Any]:
        """User implants corrective action — safe repairs + Reed handoff."""
        prop = resolve_proposal(
            self.queue_path, proposal_id, status="approved", note=note
        )
        applied = apply_safe_fixes(prop, repo_root=self.repo_root)
        prop = resolve_proposal(
            self.queue_path, proposal_id, status="applied", note=note
        )
        return {
            "proposal": prop.to_dict(),
            "applied": applied,
            "at": datetime.now(timezone.utc).isoformat(),
        }

    def reject(self, proposal_id: str, *, note: str = "") -> dict[str, Any]:
        """User declines implant — leave findings visible, no side effects."""
        prop = resolve_proposal(
            self.queue_path, proposal_id, status="rejected", note=note
        )
        return {"proposal": prop.to_dict()}

    def _dispatch_notification(
        self,
        notification: dict[str, Any],
        proposal: CorrectiveProposal,
    ) -> None:
        """Log + optional iPhone push (Aaron path). Never blocks the cycle."""
        store = self.analytics_store
        nid = None
        if store is not None:
            try:
                approval_id = store.add_approval(
                    kind="integrity_corrective",
                    title=proposal.title,
                    summary=proposal.summary,
                    payload={
                        "proposal_id": proposal.id,
                        "automatable": proposal.automatable,
                    },
                    proposal_id=proposal.id,
                )
                nid = store.log_notification(
                    kind="approval",
                    title=notification["title"],
                    message=notification["message"],
                    payload={
                        **notification,
                        "approval_id": approval_id,
                        "proposal_id": proposal.id,
                    },
                    pushed=False,
                )
                store.mark_awaiting_response(nid)
                notification["notification_id"] = nid
                notification["approval_id"] = approval_id
            except Exception:  # noqa: BLE001
                pass

        if self.notifier is None:
            return
        try:
            from aoa.notify.types import NotificationKind, StructuredNotification

            structured = StructuredNotification(
                kind=NotificationKind.APPROVAL,
                title=notification["title"],
                message=notification["message"],
                requires_response=True,
                priority=str(notification.get("priority") or "normal"),
                notification_id=nid,
                metrics={"proposal_id": proposal.id},
            )
            if hasattr(self.notifier, "send_structured"):
                self.notifier.send_structured(structured)
            elif hasattr(self.notifier, "send"):
                self.notifier.send(structured)  # type: ignore[arg-type]
            if store is not None and nid is not None:
                # Best-effort: mark pushed if send did not raise.
                pass
        except Exception:  # noqa: BLE001
            pass


def _worst_status(reports: list[DomainReport]) -> IntegritySeverity:
    order = {
        IntegritySeverity.OK: 0,
        IntegritySeverity.DEGRADED: 1,
        IntegritySeverity.CRITICAL: 2,
    }
    worst = IntegritySeverity.OK
    for r in reports:
        if order[r.status] > order[worst]:
            worst = r.status
    return worst


def _summarize(reports: list[DomainReport]) -> str:
    parts = [f"{r.agent}/{r.domain}={r.status.value}" for r in reports]
    return "; ".join(parts)


class _NullLLM:
    def structured(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    def complete(self, *args: Any, **kwargs: Any) -> str:
        return ""
