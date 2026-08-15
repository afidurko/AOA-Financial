"""Route inbound user responses to loop alerts back into concrete actions.

Aaron sends outbound alerts with ``requires_response=true``. When the user
replies — via the custom app webhook callback or the dashboard — this router
maps the reply to an action: resolve a linked approval, acknowledge an
escalation, or log for human follow-up.

Policy (loop-constraints.md): sensitive outcomes stay draft/suggest-only. The
router never edits ``.env``, enables live trading, or merges. Approve/reject is
only applied automatically when the alert is linked to a pending approval in the
inbox; anything else is recorded for a human to action.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aoa.analytics.store import AnalyticsStore

VALID_ACTIONS = ("approve", "reject", "ack")


class ResponseError(RuntimeError):
    """Raised when an inbound response cannot be routed."""


@dataclass
class ResponseResult:
    notification_id: int
    action: str
    routed_to: str
    applied: bool
    detail: str = ""

    def to_context(self) -> dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "action": self.action,
            "routed_to": self.routed_to,
            "applied": self.applied,
            "detail": self.detail,
        }


def route_response(
    store: AnalyticsStore,
    *,
    notification_id: int,
    action: str,
    note: str = "",
    actor: str = "user",
    repo_root: Path | None = None,
    integrity_queue_path: Path | None = None,
) -> ResponseResult:
    """Record the user's reply and apply the safe downstream action.

    When the alert is linked to an Integrity Ten corrective proposal, approve
    implants safe repairs (draft-PR handoff only) and reject dismisses the item.
    """
    action = action.strip().lower()
    if action not in VALID_ACTIONS:
        raise ResponseError(
            f"Unknown action {action!r}; expected one of {', '.join(VALID_ACTIONS)}."
        )

    notification = store.get_notification(notification_id)
    if notification is None:
        raise ResponseError(f"No notification with id {notification_id}.")

    recorded = store.record_response(
        notification_id, action=action, note=note, actor=actor
    )
    if not recorded:
        raise ResponseError(
            f"Notification {notification_id} was already responded to."
        )

    payload = notification.get("payload") or {}
    approval_id = payload.get("approval_id")
    proposal_id = payload.get("proposal_id")

    # Integrity Ten — implant / dismiss via Needs Attention or alert reply.
    if action in ("approve", "reject") and proposal_id:
        try:
            applied_detail = _apply_integrity_decision(
                str(proposal_id),
                action=action,
                note=note,
                repo_root=repo_root or Path.cwd(),
                queue_path=integrity_queue_path,
            )
            if approval_id:
                store.resolve_approval(
                    str(approval_id),
                    "approved" if action == "approve" else "rejected",
                )
            return ResponseResult(
                notification_id=notification_id,
                action=action,
                routed_to="integrity_queue",
                applied=True,
                detail=applied_detail,
            )
        except Exception as exc:  # noqa: BLE001
            raise ResponseError(f"Integrity action failed: {exc}") from exc

    if action in ("approve", "reject") and approval_id:
        status = "approved" if action == "approve" else "rejected"
        applied = store.resolve_approval(str(approval_id), status)
        return ResponseResult(
            notification_id=notification_id,
            action=action,
            routed_to="approval_inbox",
            applied=applied,
            detail=(
                f"Approval {approval_id} -> {status}"
                if applied
                else f"Approval {approval_id} was not pending"
            ),
        )

    if action == "ack":
        return ResponseResult(
            notification_id=notification_id,
            action=action,
            routed_to="acknowledged",
            applied=True,
            detail=f"Acknowledged: {notification.get('title', '')}",
        )

    return ResponseResult(
        notification_id=notification_id,
        action=action,
        routed_to="logged",
        applied=False,
        detail="No linked approval; recorded for human follow-up (draft-only).",
    )


def _apply_integrity_decision(
    proposal_id: str,
    *,
    action: str,
    note: str,
    repo_root: Path,
    queue_path: Path | None,
) -> str:
    from aoa.config import data_dir_for
    from aoa.integrity.squad import IntegritySquad

    data_dir = queue_path.parent if queue_path is not None else None
    if data_dir is None:
        for env in ("paper-dry", "paper"):
            candidate = data_dir_for(env) / "integrity"
            if (candidate / "corrective_queue.json").is_file():
                data_dir = candidate
                break
        if data_dir is None:
            data_dir = repo_root / "data" / "paper-dry" / "integrity"

    squad = IntegritySquad(repo_root=repo_root, data_dir=data_dir)
    if queue_path is not None:
        squad.queue_path = queue_path
    if action == "approve":
        squad.approve(proposal_id, note=note)
        return f"Integrity {proposal_id} implanted (draft-PR only)."
    squad.reject(proposal_id, note=note)
    return f"Integrity {proposal_id} rejected (no implant)."
