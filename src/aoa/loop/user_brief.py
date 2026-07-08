"""Loop-aware user brief — one summary covering trading and the engineering loop.

Alex (the executive assistant) prioritizes trading and approval items. This
module folds in loop-engineering state — the High Priority / Watch List sections
of ``STATE.md`` and the Fable 5 repair queue — so a single daily brief covers
both, and attaches ready-to-send replies for any alerts awaiting a response.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aoa.team.models import AssistantBrief

_STATE_ITEM_RE = re.compile(r"- \*\*(.+?)\*\*(?: — (.+))?")


@dataclass
class LoopStateSummary:
    """High Priority and Watch List items parsed from STATE.md."""

    high_priority: list[dict[str, str]] = field(default_factory=list)
    watch: list[dict[str, str]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.high_priority and not self.watch


def parse_state_md(state_path: Path) -> LoopStateSummary:
    """Extract loop High Priority and Watch List bullets from STATE.md."""
    summary = LoopStateSummary()
    if not state_path.is_file():
        return summary
    section = ""
    for line in state_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## High Priority"):
            section = "high"
            continue
        if line.startswith("## Watch List"):
            section = "watch"
            continue
        if line.startswith("## "):
            section = ""
            continue
        stripped = line.strip()
        if section not in {"high", "watch"} or not stripped.startswith("- **"):
            continue
        match = _STATE_ITEM_RE.match(stripped)
        if not match:
            continue
        title = match.group(1).strip()
        detail = (match.group(2) or "").strip()
        if title.startswith("_") or "none" in title.lower():
            continue
        bucket = summary.high_priority if section == "high" else summary.watch
        bucket.append({"title": title, "detail": detail})
    return summary


def repair_queue_summary(repair_path: Path) -> dict[str, int]:
    """Count total and fixable items in the repair queue without side effects."""
    queue_file = Path(repair_path) / "queue.json"
    if not queue_file.is_file():
        return {"count": 0, "fixable": 0}
    try:
        data = json.loads(queue_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"count": 0, "fixable": 0}
    items = data.get("items", [])
    return {
        "count": len(items),
        "fixable": sum(1 for i in items if i.get("fixable")),
    }


@dataclass
class SuggestedReply:
    """A one-tap reply the user can send back to an alert awaiting a response."""

    prompt: str
    action: str
    target: str = ""

    def to_context(self) -> dict[str, Any]:
        return {"prompt": self.prompt, "action": self.action, "target": self.target}


@dataclass
class LoopUserBrief:
    """User-facing brief combining Alex priorities, loop state, and reply options."""

    summary: str = ""
    focus: str = ""
    must_do: list[dict[str, Any]] = field(default_factory=list)
    should_do: list[dict[str, Any]] = field(default_factory=list)
    can_wait: list[dict[str, Any]] = field(default_factory=list)
    repair_queue: dict[str, int] = field(default_factory=dict)
    suggested_replies: list[SuggestedReply] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "focus": self.focus,
            "must_do": self.must_do,
            "should_do": self.should_do,
            "can_wait": self.can_wait,
            "repair_queue": self.repair_queue,
            "suggested_replies": [r.to_context() for r in self.suggested_replies],
        }


def build_loop_user_brief(
    *,
    assistant_brief: AssistantBrief,
    repair_summary: dict[str, int] | None = None,
    pending_responses: list[dict[str, Any]] | None = None,
) -> LoopUserBrief:
    """Wrap Alex's brief with repair-queue context and per-alert reply options."""
    repair = repair_summary or {"count": 0, "fixable": 0}
    replies: list[SuggestedReply] = []
    for note in pending_responses or []:
        nid = str(note.get("id", ""))
        title = note.get("title", "alert")
        replies.append(SuggestedReply(f"Approve: {title}", "approve", nid))
        replies.append(SuggestedReply(f"Reject: {title}", "reject", nid))

    summary = assistant_brief.summary or "Loop steady; no blockers."
    if repair.get("fixable"):
        summary = f"{summary} ({repair['fixable']} fixable repair item(s) queued)."

    return LoopUserBrief(
        summary=summary,
        focus=assistant_brief.focus,
        must_do=[i.to_context() for i in assistant_brief.must_do],
        should_do=[i.to_context() for i in assistant_brief.should_do],
        can_wait=[i.to_context() for i in assistant_brief.can_wait],
        repair_queue=repair,
        suggested_replies=replies,
    )


def deliver_loop_brief(brief: LoopUserBrief, notifier: Any) -> list[str]:
    """Push the brief to the user's iPhone. Returns the channels used."""
    from aoa.notify.iphone import IPhoneNotification, NotificationReason

    lines = [brief.summary]
    for item in brief.must_do:
        lines.append(f"MUST: {item['title']}")
    message = "\n".join(lines)[:600]
    reason = (
        NotificationReason.NEEDS_VERIFICATION
        if brief.suggested_replies
        else NotificationReason.INFORM
    )
    return notifier.send(
        IPhoneNotification(
            title="AOA — daily loop brief",
            message=message,
            reason=reason,
        )
    )
