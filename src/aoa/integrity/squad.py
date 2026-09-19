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
        from aoa.integrity.notify import notify_status_payload, pending_queue_items

        cs = load_constraints(self.repo_root)
        pending = [p.to_dict() for p in pending_queue_items(self.queue_path)]
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
            "notify": notify_status_payload(self.notifier),
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
                    from aoa.integrity.attention import write_cursor_attention_file

                    attention_path = write_cursor_attention_file(self.queue_path)
                    notes.append(
                        f"Cursor Needs Attention payload: {attention_path}"
                    )
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

    def notify_queue(self, *, digest: bool = True, force: bool = False) -> dict[str, Any]:
        """Push notifications for pending corrective-queue items (Aaron path)."""
        from aoa.integrity.notify import (
            build_queue_notifications,
            notify_status_payload,
            pending_queue_items,
        )

        pending = pending_queue_items(self.queue_path)
        notify_info = notify_status_payload(self.notifier)
        result: dict[str, Any] = {
            "pending": len(pending),
            "proposals": [p.id for p in pending],
            "notify": notify_info,
            "pushed": False,
            "channels": [],
            "logged": 0,
            "detail": "",
        }
        if not pending:
            result["detail"] = "Queue empty — nothing to notify."
            return result

        payloads = build_queue_notifications(pending, digest=digest)
        channels: list[str] = []
        logged = 0
        for payload in payloads:
            proposal = pending[0] if digest else next(
                (p for p in pending if p.id == payload.get("proposal_id")), pending[0]
            )
            self._dispatch_notification(payload, proposal)
            logged += 1
            channels.extend(list(payload.get("channels") or []))

        result["logged"] = logged
        result["channels"] = sorted(set(channels))
        result["pushed"] = bool(result["channels"])
        from aoa.integrity.attention import write_cursor_attention_file

        attention_path = write_cursor_attention_file(self.queue_path)
        result["cursor_attention"] = str(attention_path)
        if not notify_info.get("configured") and not force:
            result["detail"] = (
                notify_info.get("setup_hint")
                or "Notify not configured — queue logged only."
            )
        elif result["pushed"]:
            result["detail"] = f"Pushed via {', '.join(result['channels'])}."
        else:
            result["detail"] = "Notifications logged; push channel unavailable."
        result["detail"] += (
            " Surface in Cursor via: aoa integrity attention --cursor"
        )
        return result

    def _dispatch_notification(
        self,
        notification: dict[str, Any],
        proposal: CorrectiveProposal,
    ) -> None:
        """Log + optional iPhone push (Aaron path). Never blocks the cycle."""
        store = self.analytics_store
        nid = None
        notification.setdefault("channels", [])
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
                        **{
                            k: v
                            for k, v in notification.items()
                            if k != "channels"
                        },
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

        if self.notifier is None or not getattr(self.notifier, "configured", False):
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
                metrics={
                    "proposal_id": proposal.id,
                    "proposal_ids": notification.get("proposal_ids") or [proposal.id],
                },
            )
            channels: list[str] = []
            if hasattr(self.notifier, "send_structured"):
                channels = list(self.notifier.send_structured(structured) or [])
            elif hasattr(self.notifier, "send"):
                from aoa.notify.iphone import IPhoneNotification, NotificationReason

                channels = list(
                    self.notifier.send(
                        IPhoneNotification(
                            title=notification["title"],
                            message=notification["message"],
                            reason=NotificationReason.NEEDS_VERIFICATION,
                        )
                    )
                    or []
                )
            notification["channels"] = channels
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
