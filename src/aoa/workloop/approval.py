"""Aaron / user approval gate for work-loop execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aoa.workloop.store import WorkloopStore


class ApprovalRequired(RuntimeError):
    """Raised when a run must pause until the configured approver signs off."""


class TeamRejected(RuntimeError):
    """Raised when the meshed team rejects a change proposal."""


def required_approver_for_run(run, config) -> str:
    review = getattr(run, "team_review", None) or {}
    return str(review.get("required_approver") or config.workloop_approver)


def check_team_review_gate(team_review: dict[str, Any] | None) -> None:
    if not team_review:
        return
    verdict = team_review.get("verdict")
    if verdict == "reject":
        summary = team_review.get("summary") or "Change rejected by team review."
        raise TeamRejected(summary)


def check_approval(
    store: WorkloopStore,
    *,
    run_id: str,
    approver: str,
) -> dict[str, Any]:
    approval = store.load_approval()
    if approval is None:
        raise ApprovalRequired(
            f"Approval required from {approver}. "
            f"Run: aoa workloop approve --approver {approver}"
        )
    if approval.get("run_id") != run_id:
        raise ApprovalRequired(
            f"Stale approval for run {approval.get('run_id')!r}; "
            f"current run is {run_id!r}. Re-approve with aoa workloop approve."
        )
    if approval.get("approver") != approver:
        raise ApprovalRequired(
            f"Approver mismatch: expected {approver!r}, got {approval.get('approver')!r}."
        )
    return approval


def record_approval(
    store: WorkloopStore,
    *,
    run_id: str,
    approver: str,
    note: str = "",
) -> dict[str, Any]:
    approval = {
        "run_id": run_id,
        "approver": approver,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
    }
    store.save_approval(approval)
    store.record("workloop.approved", approval)
    return approval
