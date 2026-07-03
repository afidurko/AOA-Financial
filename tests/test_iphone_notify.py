"""Tests for iPhone push notifications."""

from __future__ import annotations

import pytest

from aoa.notify.iphone import (
    IPhoneNotification,
    IPhoneNotifier,
    NotificationError,
    NotificationReason,
)


def test_notifier_not_configured_raises():
    notifier = IPhoneNotifier()
    assert notifier.configured is False
    with pytest.raises(NotificationError, match="not configured"):
        notifier.send(
            IPhoneNotification(title="t", message="m", reason=NotificationReason.UNFIXABLE)
        )


def test_pushover_send(monkeypatch):
    calls = []

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResp()

    monkeypatch.setattr("aoa.notify.iphone.httpx.post", fake_post)
    notifier = IPhoneNotifier(pushover_user_key="user", pushover_app_token="app")
    channels = notifier.send(
        IPhoneNotification(
            title="AOA",
            message="Broker down",
            reason=NotificationReason.UNFIXABLE,
        )
    )
    assert channels == ["pushover"]
    assert "pushover.net" in calls[0][0]
    assert calls[0][1]["data"]["user"] == "user"


def test_ntfy_send(monkeypatch):
    calls = []

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResp()

    monkeypatch.setattr("aoa.notify.iphone.httpx.post", fake_post)
    notifier = IPhoneNotifier(ntfy_topic="my-alerts")
    channels = notifier.send(
        IPhoneNotification(
            title="AOA",
            message="Confirm live trading",
            reason=NotificationReason.NEEDS_VERIFICATION,
        )
    )
    assert channels == ["ntfy"]
    assert calls[0][0].endswith("/my-alerts")
