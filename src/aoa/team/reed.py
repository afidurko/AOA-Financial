"""Reed — task-loop architect and implementer (ATTL factory + maker handoff)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aoa.agents.base import Agent


class ReedAgent(Agent):
    name = "reed"
    display_name = "Reed"
    role = "Task-Loop Architect & Implementer"

    system_prompt = (
        "You are Reed, the task-loop architect on the AOA twelve-member team. "
        "You create coding tasks from repair/backlog signals and hand off "
        "implementation. You mesh with Julie (algorithms) and Nova (brain). "
        "You do not perform mandatory code review — Kai handles critical-only review."
    )

    def propose_tasks(
        self,
        *,
        repair_items: list[dict[str, Any]] | None = None,
        backlog_items: list[dict[str, Any]] | None = None,
        out_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Auto-create prioritized task definitions (no human activate step)."""
        proposed: list[dict[str, Any]] = []
        for item in repair_items or []:
            item_id = str(
                item.get("item_id") or item.get("id") or item.get("key") or "unknown"
            )
            title = str(
                item.get("title") or item.get("summary") or item_id
            )
            escalated = bool(item.get("requires_escalation", False))
            fixable = item.get("fixable")
            if fixable is None:
                fixable = not escalated
            proposed.append(
                {
                    "id": f"repair-{item_id}",
                    "item_id": item_id,
                    "source": "repair",
                    "title": title,
                    "priority": str(item.get("severity") or item.get("priority") or "medium"),
                    "automatable": bool(fixable) and not escalated,
                    "detail": item.get("detail") or item.get("summary") or "",
                    "skill": item.get("suggested_skill") or "minimal-fix",
                }
            )
        for item in backlog_items or []:
            proposed.append(
                {
                    "id": str(item.get("id") or item.get("key") or "backlog"),
                    "item_id": str(item.get("id") or item.get("key") or "backlog"),
                    "source": "backlog",
                    "title": item.get("title", ""),
                    "priority": "planned",
                    "automatable": bool(item.get("automatable", False)),
                    "detail": item.get("detail", ""),
                    "skill": item.get("skill", "minimal-fix"),
                }
            )
        # Need-order: repair automatable first, then backlog automatable, then rest
        proposed.sort(
            key=lambda t: (
                0 if t.get("source") == "repair" and t.get("automatable") else
                1 if t.get("automatable") else 2,
                str(t.get("id")),
            )
        )
        written: Path | None = None
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            written = out_dir / "proposed-tasks.json"
            written.write_text(json.dumps({"tasks": proposed}, indent=2), encoding="utf-8")
        return {
            "agent": self.display_name,
            "role": self.role,
            "count": len(proposed),
            "tasks": proposed,
            "path": str(written) if written else "",
        }
