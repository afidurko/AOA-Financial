"""Repair-loop data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepairItem:
    item_id: str
    title: str
    source: str  # code_audit | verify | state | team_health
    severity: str  # critical | degraded | watch
    fixable: bool
    detail: str = ""
    suggested_skill: str = "minimal-fix"
    status: str = "queued"  # queued | in_progress | fixed | escalated | ignored

    def to_context(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "source": self.source,
            "severity": self.severity,
            "fixable": self.fixable,
            "detail": self.detail,
            "suggested_skill": self.suggested_skill,
            "status": self.status,
        }

    @classmethod
    def from_context(cls, data: dict[str, Any]) -> RepairItem:
        return cls(
            item_id=str(data.get("item_id", "")),
            title=str(data.get("title", "")),
            source=str(data.get("source", "")),
            severity=str(data.get("severity", "watch")),
            fixable=bool(data.get("fixable", False)),
            detail=str(data.get("detail", "")),
            suggested_skill=str(data.get("suggested_skill", "minimal-fix")),
            status=str(data.get("status", "queued")),
        )


@dataclass
class RepairRun:
    run_id: str
    status: str = "completed"
    items: list[RepairItem] = field(default_factory=list)
    verify: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "items": [i.to_context() for i in self.items],
            "verify": self.verify,
            "notes": self.notes,
        }

    @classmethod
    def from_context(cls, data: dict[str, Any]) -> RepairRun:
        return cls(
            run_id=str(data.get("run_id", "")),
            status=str(data.get("status", "completed")),
            items=[RepairItem.from_context(i) for i in data.get("items", [])],
            verify=dict(data.get("verify", {})),
            notes=list(data.get("notes", [])),
        )
