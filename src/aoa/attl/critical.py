"""Critical-only review detector for ATTL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CriticalSignal:
    critical: bool = False
    system_failure: bool = False
    report_requested: bool = False
    summary: str = ""
    detail: str = ""
    sources: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.critical or self.system_failure or self.report_requested

    def to_dict(self) -> dict[str, Any]:
        return {
            "critical": self.critical,
            "system_failure": self.system_failure,
            "report_requested": self.report_requested,
            "summary": self.summary,
            "detail": self.detail,
            "sources": list(self.sources),
            "needs_review": self.needs_review,
        }


def detect_critical(
    *,
    bob_can_proceed: bool | None = None,
    bob_summary: str = "",
    gate_action: str = "",
    verify_ok: bool | None = None,
    worktree_ok: bool | None = None,
    report_requested: bool = False,
    extra_detail: str = "",
) -> CriticalSignal:
    """Build a CriticalSignal from health/gate/verify inputs."""
    signal = CriticalSignal(report_requested=report_requested, detail=extra_detail)
    if bob_can_proceed is False:
        signal.critical = True
        signal.sources.append("bob")
        signal.summary = bob_summary or "Bob health/code integrity blocked proceed."
    if gate_action in {"pause"}:
        signal.system_failure = True
        signal.sources.append("gate")
        signal.summary = signal.summary or f"Gate action={gate_action}"
    if verify_ok is False:
        signal.critical = True
        signal.sources.append("verify")
        signal.summary = signal.summary or "Verify (ruff/pytest) failed."
    if worktree_ok is False:
        signal.system_failure = True
        signal.sources.append("worktree")
        signal.summary = signal.summary or "Worktree creation/setup failed."
    if report_requested and not signal.summary:
        signal.summary = "Explicit ATTL report requested."
    return signal
