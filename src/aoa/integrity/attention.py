"""Needs Attention bridge — Integrity queue ↔ Cursor + dashboard.

Cursor Cloud's **Needs Attention** tab is fed by
``request-environment-setup-actions`` MCP calls (``external_action`` items).
This module builds those payloads from the Integrity Ten corrective queue so
agents can surface approve/reject work inside Cursor, not only via iPhone push.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.integrity.actions import CorrectiveProposal, load_queue
from aoa.integrity.notify import pending_queue_items


@dataclass
class AttentionItem:
    """One user-facing item for the Needs Attention surface."""

    id: str
    source: str  # integrity | alert | approval
    title: str
    detail: str
    actions: list[dict[str, str]] = field(default_factory=list)
    priority: str = "normal"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "detail": self.detail,
            "actions": list(self.actions),
            "priority": self.priority,
            "payload": dict(self.payload),
        }


def integrity_attention_items(queue_path: Path) -> list[AttentionItem]:
    """Build Needs Attention rows from pending integrity proposals."""
    items: list[AttentionItem] = []
    for prop in pending_queue_items(queue_path):
        critical = any(f.get("status") == "critical" for f in prop.findings)
        items.append(
            AttentionItem(
                id=prop.id,
                source="integrity",
                title=prop.title,
                detail=prop.summary,
                priority="high" if critical else "normal",
                actions=[
                    {
                        "id": "approve",
                        "label": "Approve implant",
                        "command": f"aoa integrity approve {prop.id}",
                    },
                    {
                        "id": "reject",
                        "label": "Reject",
                        "command": f"aoa integrity reject {prop.id}",
                    },
                ],
                payload={
                    "proposal_id": prop.id,
                    "automatable": prop.automatable,
                    "findings": prop.findings,
                    "created_at": prop.created_at,
                },
            )
        )
    return items


def cursor_external_actions(
    items: list[AttentionItem],
) -> list[dict[str, str]]:
    """Map attention items to Cursor MCP ``external_action`` objects.

    These are accepted by ``cursor-cloud`` /
    ``request-environment-setup-actions`` and appear under Needs Attention.
    """
    actions: list[dict[str, str]] = []
    for item in items:
        if item.source != "integrity":
            continue
        pid = item.id
        actions.append(
            {
                "type": "external_action",
                "id": f"integrity-approve-{pid}",
                "title": f"Approve integrity fix: {pid}",
                "instructions": (
                    f"{item.title}\n\n{item.detail}\n\n"
                    f"In Cursor chat or terminal run:\n"
                    f"  aoa integrity approve {pid}\n\n"
                    "This implants safe repairs and queues a Reed draft-PR "
                    "handoff. Never auto-merges."
                ),
            }
        )
        actions.append(
            {
                "type": "external_action",
                "id": f"integrity-reject-{pid}",
                "title": f"Reject integrity fix: {pid}",
                "instructions": (
                    f"Decline implant for {pid}.\n\n"
                    f"Run: aoa integrity reject {pid}\n\n"
                    "Findings stay visible; no code side effects."
                ),
            }
        )
    return actions


def cursor_mcp_payload(queue_path: Path) -> dict[str, Any]:
    """Full payload ready for request-environment-setup-actions."""
    items = integrity_attention_items(queue_path)
    actions = cursor_external_actions(items)
    return {
        "source": "aoa.integrity",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pending": len(items),
        "items": [i.to_dict() for i in items],
        "actions": actions,
        "mcp_tool": "request-environment-setup-actions",
        "mcp_server": "cursor-cloud",
        "hint": (
            "Cloud agents: CallMcpTool server=cursor-cloud "
            "toolName=request-environment-setup-actions with actions=…"
            if actions
            else "Queue empty — nothing to surface in Needs Attention."
        ),
    }


def write_cursor_attention_file(
    queue_path: Path,
    *,
    out_path: Path | None = None,
) -> Path:
    """Persist Cursor Needs Attention payload next to the corrective queue."""
    payload = cursor_mcp_payload(queue_path)
    path = out_path or (queue_path.parent / "cursor_needs_attention.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def needs_attention_feed(
    *,
    integrity_queue_path: Path,
    pending_alerts: list[dict[str, Any]] | None = None,
    pending_approvals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate Integrity + alerts + approvals for the dashboard tab."""
    integrity = integrity_attention_items(integrity_queue_path)
    alerts: list[AttentionItem] = []
    for note in pending_alerts or []:
        nid = str(note.get("id", ""))
        alerts.append(
            AttentionItem(
                id=f"alert-{nid}",
                source="alert",
                title=str(note.get("title") or "Alert"),
                detail=str(note.get("message") or ""),
                priority="high",
                actions=[
                    {
                        "id": "approve",
                        "label": "Approve",
                        "command": f"POST /api/alerts/{nid}/respond action=approve",
                    },
                    {
                        "id": "reject",
                        "label": "Reject",
                        "command": f"POST /api/alerts/{nid}/respond action=reject",
                    },
                ],
                payload={"notification_id": note.get("id"), "raw": note},
            )
        )
    approvals: list[AttentionItem] = []
    for row in pending_approvals or []:
        if str(row.get("status")) != "pending":
            continue
        # Skip integrity rows already listed from the queue file.
        kind = str(row.get("kind") or "")
        if kind == "integrity_corrective":
            continue
        aid = str(row.get("id", ""))
        approvals.append(
            AttentionItem(
                id=f"approval-{aid}",
                source="approval",
                title=str(row.get("title") or "Approval"),
                detail=str(row.get("summary") or ""),
                actions=[
                    {
                        "id": "approve",
                        "label": "Approve",
                        "command": f"POST /api/approvals/{aid}/resolve status=approved",
                    },
                    {
                        "id": "reject",
                        "label": "Reject",
                        "command": f"POST /api/approvals/{aid}/resolve status=rejected",
                    },
                ],
                payload={"approval_id": aid, "kind": kind},
            )
        )

    all_items = integrity + alerts + approvals
    return {
        "count": len(all_items),
        "integrity_pending": len(integrity),
        "items": [i.to_dict() for i in all_items],
        "cursor": cursor_mcp_payload(integrity_queue_path),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def proposals_from_queue(queue_path: Path) -> list[CorrectiveProposal]:
    return load_queue(queue_path)
