"""Queue notification helpers for Integrity Ten corrective proposals."""

from __future__ import annotations

from typing import Any

from aoa.integrity.actions import CorrectiveProposal, build_user_notification, load_queue


def pending_queue_items(queue_path) -> list[CorrectiveProposal]:
    return [p for p in load_queue(queue_path) if p.status == "pending"]


def queue_digest_message(pending: list[CorrectiveProposal]) -> str:
    if not pending:
        return "Integrity corrective queue is empty."
    lines = [
        f"Integrity Ten queue: {len(pending)} pending corrective "
        f"action{'s' if len(pending) != 1 else ''} awaiting your approve/reject.",
        "",
    ]
    for prop in pending[:8]:
        lines.append(f"• {prop.id}: {prop.title}")
        lines.append(f"  aoa integrity approve {prop.id}")
        lines.append(f"  aoa integrity reject {prop.id}")
    if len(pending) > 8:
        lines.append(f"… and {len(pending) - 8} more")
    lines.append("")
    lines.append("Implant only after approve. Never auto-merge.")
    return "\n".join(lines)


def notify_status_payload(notifier: Any) -> dict[str, Any]:
    if notifier is None:
        return {
            "configured": False,
            "channels": [],
            "setup_hint": (
                "Wire IPhoneNotifier from Config (AOA_NTFY_TOPIC / Pushover / webhook)."
            ),
        }
    if hasattr(notifier, "status"):
        return dict(notifier.status())
    return {
        "configured": bool(getattr(notifier, "configured", False)),
        "channels": list(getattr(notifier, "channel_names", lambda: [])()),
    }


def build_queue_notifications(
    pending: list[CorrectiveProposal],
    *,
    digest: bool = True,
) -> list[dict[str, Any]]:
    """Build notification payloads for pending queue items.

    When ``digest`` is True (default), one summary alert covers the queue.
    Otherwise each proposal gets its own approval alert.
    """
    if not pending:
        return []
    if digest:
        return [
            {
                "kind": "approval",
                "title": f"Integrity queue — {len(pending)} pending",
                "message": queue_digest_message(pending),
                "requires_response": True,
                "priority": "high"
                if any(
                    any(f.get("status") == "critical" for f in p.findings)
                    for p in pending
                )
                else "normal",
                "proposal_ids": [p.id for p in pending],
            }
        ]
    return [build_user_notification(p) for p in pending]
