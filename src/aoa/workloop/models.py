"""Work-loop data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STAGE_ORDER = (
    "discover",
    "extract",
    "adapt",
    "vault_sync",
    "propose",
    "team_review",
    "approval",
    "execute",
    "verify",
    "upgrade",
    "reverify",
    "merge",
)


@dataclass
class LearningSource:
    kind: str
    path: str
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "summary": self.summary,
            "metadata": self.metadata,
        }


@dataclass
class WorkloopRun:
    run_id: str
    stage: str = "discover"
    status: str = "running"  # running | awaiting_approval | completed | failed
    discovered: list[dict[str, Any]] = field(default_factory=list)
    extracted: dict[str, Any] = field(default_factory=dict)
    adaptations: list[dict[str, Any]] = field(default_factory=list)
    proposal: dict[str, Any] = field(default_factory=dict)
    team_review: dict[str, Any] = field(default_factory=dict)
    approval: dict[str, Any] | None = None
    execution: dict[str, Any] = field(default_factory=dict)
    verify: dict[str, Any] = field(default_factory=dict)
    upgrade: dict[str, Any] = field(default_factory=dict)
    reverify: dict[str, Any] = field(default_factory=dict)
    merge: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: str = ""
    iteration: int = 0
    previous_run_id: str = ""

    def to_context(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stage": self.stage,
            "status": self.status,
            "discovered": self.discovered,
            "extracted": self.extracted,
            "adaptations": self.adaptations,
            "proposal": self.proposal,
            "team_review": self.team_review,
            "approval": self.approval,
            "execution": self.execution,
            "verify": self.verify,
            "upgrade": self.upgrade,
            "reverify": self.reverify,
            "merge": self.merge,
            "notes": self.notes,
            "error": self.error,
            "iteration": self.iteration,
            "previous_run_id": self.previous_run_id,
        }

    @classmethod
    def from_context(cls, data: dict[str, Any]) -> WorkloopRun:
        return cls(
            run_id=str(data.get("run_id", "")),
            stage=str(data.get("stage", "discover")),
            status=str(data.get("status", "running")),
            discovered=list(data.get("discovered", [])),
            extracted=dict(data.get("extracted", {})),
            adaptations=list(data.get("adaptations", [])),
            proposal=dict(data.get("proposal", {})),
            team_review=dict(data.get("team_review", {})),
            approval=data.get("approval"),
            execution=dict(data.get("execution", {})),
            verify=dict(data.get("verify", {})),
            upgrade=dict(data.get("upgrade", {})),
            reverify=dict(data.get("reverify", {})),
            merge=dict(data.get("merge", {})),
            notes=list(data.get("notes", [])),
            error=str(data.get("error", "")),
            iteration=int(data.get("iteration", 0) or 0),
            previous_run_id=str(data.get("previous_run_id", "")),
        )
