"""Tests for the inbound response router and notification response tracking."""

from __future__ import annotations

import pytest

from aoa.analytics.store import AnalyticsStore
from aoa.notify.response_router import ResponseError, route_response


def _store(tmp_path):
    return AnalyticsStore(tmp_path / "a.sqlite")


def test_record_and_list_pending_responses(tmp_path):
    store = _store(tmp_path)
    nid = store.log_notification(kind="alert", title="Verify", message="ok?")
    assert store.mark_awaiting_response(nid) is True
    pending = store.list_pending_responses()
    assert [p["id"] for p in pending] == [nid]
    store.close()


def test_route_response_resolves_linked_approval(tmp_path):
    store = _store(tmp_path)
    approval_id = store.add_approval(
        kind="workloop", title="Merge prep", summary="Approve run"
    )
    nid = store.log_notification(
        kind="escalation",
        title="Approve run",
        message="Confirm",
        payload={"approval_id": approval_id, "reason": "needs_verification"},
    )
    store.mark_awaiting_response(nid)

    result = route_response(store, notification_id=nid, action="approve")
    assert result.routed_to == "approval_inbox"
    assert result.applied is True
    approvals = store.list_approvals(status="approved")
    assert any(a["id"] == approval_id for a in approvals)
    # The notification is now marked responded and no longer pending.
    assert store.list_pending_responses() == []
    store.close()


def test_route_response_ack(tmp_path):
    store = _store(tmp_path)
    nid = store.log_notification(kind="alert", title="Heads up", message="fyi")
    store.mark_awaiting_response(nid)
    result = route_response(store, notification_id=nid, action="ack", note="seen")
    assert result.routed_to == "acknowledged"
    assert result.applied is True
    store.close()


def test_route_response_without_linked_approval_logs_only(tmp_path):
    store = _store(tmp_path)
    nid = store.log_notification(kind="alert", title="Odd", message="no approval")
    store.mark_awaiting_response(nid)
    result = route_response(store, notification_id=nid, action="approve")
    assert result.routed_to == "logged"
    assert result.applied is False
    store.close()


def test_route_response_invalid_action(tmp_path):
    store = _store(tmp_path)
    nid = store.log_notification(kind="alert", title="X", message="y")
    store.mark_awaiting_response(nid)
    with pytest.raises(ResponseError):
        route_response(store, notification_id=nid, action="delete")
    store.close()


def test_route_response_unknown_notification(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ResponseError):
        route_response(store, notification_id=999, action="ack")
    store.close()


def test_route_response_integrity_proposal_ids(tmp_path):

    from aoa.integrity.actions import propose_from_reports
    from aoa.integrity.checks import DomainReport, IntegrityFinding, IntegritySeverity
    from aoa.integrity.squad import IntegritySquad

    # Minimal brain for implant
    root = tmp_path / "repo"
    (root / "brain" / "captures").mkdir(parents=True)
    (root / "brain" / "decisions").mkdir(parents=True)
    (root / "brain" / "mesh").mkdir(parents=True)
    for rel in (
        "brain/_CLAUDE.md",
        "brain/README.md",
        "brain/spine/ATTL.md",
        "brain/spine/Algorithms.md",
        "brain/spine/Team-Mesh.md",
        "brain/mesh/index.yaml",
        "brain/mesh/repos.yaml",
    ):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("x\n", encoding="utf-8")

    queue = tmp_path / "integrity" / "corrective_queue.json"
    queue.parent.mkdir(parents=True)
    prop = propose_from_reports(
        [
            DomainReport(
                domain="code",
                agent="Bob",
                status=IntegritySeverity.DEGRADED,
                findings=[
                    IntegrityFinding(
                        domain="code",
                        agent="Bob",
                        status=IntegritySeverity.DEGRADED,
                        detail="router implant",
                        automatable=True,
                    )
                ],
                summary="router",
            )
        ],
        queue_path=queue,
    )
    assert prop is not None

    store = _store(tmp_path)
    approval_id = store.add_approval(
        kind="integrity_corrective",
        title=prop.title,
        summary=prop.summary,
        payload={"proposal_id": prop.id},
        proposal_id=prop.id,
    )
    nid = store.log_notification(
        kind="approval",
        title=prop.title,
        message="approve?",
        payload={
            "approval_id": approval_id,
            "proposal_id": prop.id,
            "proposal_ids": [prop.id],
        },
    )
    store.mark_awaiting_response(nid)

    result = route_response(
        store,
        notification_id=nid,
        action="approve",
        repo_root=root,
        integrity_queue_path=queue,
    )
    assert result.routed_to == "integrity_queue"
    assert result.applied is True
    squad = IntegritySquad(repo_root=root, data_dir=queue.parent)
    squad.queue_path = queue
    assert all(p.status != "pending" for p in __import__(
        "aoa.integrity.actions", fromlist=["load_queue"]
    ).load_queue(queue))
    assert store.list_pending_responses() == []
    store.close()


def test_route_response_double_reply_rejected(tmp_path):
    store = _store(tmp_path)
    nid = store.log_notification(kind="alert", title="X", message="y")
    store.mark_awaiting_response(nid)
    route_response(store, notification_id=nid, action="ack")
    with pytest.raises(ResponseError):
        route_response(store, notification_id=nid, action="ack")
    store.close()


def test_route_response_keeps_alert_when_integrity_fails(tmp_path):
    store = _store(tmp_path)
    nid = store.log_notification(
        kind="approval",
        title="missing",
        message="approve?",
        payload={"proposal_id": "int-missing", "proposal_ids": ["int-missing"]},
    )
    store.mark_awaiting_response(nid)
    with pytest.raises(ResponseError):
        route_response(
            store,
            notification_id=nid,
            action="approve",
            repo_root=tmp_path,
            integrity_queue_path=tmp_path / "no-queue.json",
        )
    # Alert must remain awaiting so the user can retry after fixing the queue.
    assert [p["id"] for p in store.list_pending_responses()] == [nid]
    store.close()
