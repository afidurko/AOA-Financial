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


def test_route_response_double_reply_rejected(tmp_path):
    store = _store(tmp_path)
    nid = store.log_notification(kind="alert", title="X", message="y")
    store.mark_awaiting_response(nid)
    route_response(store, notification_id=nid, action="ack")
    with pytest.raises(ResponseError):
        route_response(store, notification_id=nid, action="ack")
    store.close()
