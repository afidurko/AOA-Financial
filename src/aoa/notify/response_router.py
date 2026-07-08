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
) -> ResponseResult:
    """Record a user's reply to a notification and apply the safe downstream action."""
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
