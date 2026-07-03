"""Tests for custom app webhook notifications."""

from __future__ import annotations

import pytest

from aoa.notify.custom_app import (
    NotificationError,
    build_custom_app_payload,
    send_custom_app_webhook,
)
from aoa.notify.iphone import IPhoneNotification, IPhoneNotifier, NotificationReason


def test_custom_app_payload():
    payload = build_custom_app_payload(
        title="AOA",
        message="Broker down",
        reason="unfixable",
        device_id="device-1",
    )
    assert payload["source"] == "aoa-financial"
    assert payload["requires_response"] is False
    assert payload["priority"] == "high"
    assert payload["device_id"] == "device-1"


def test_custom_app_payload_verification():
    payload = build_custom_app_payload(
        title="AOA",
        message="Confirm live trading",
        reason="needs_verification",
    )
    assert payload["requires_response"] is True
    assert payload["priority"] == "normal"


def test_custom_app_webhook_send(monkeypatch):
    calls = []

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResp()

    monkeypatch.setattr("aoa.notify.custom_app.httpx.post", fake_post)
    send_custom_app_webhook(
        "https://app.example/alerts",
        title="AOA",
        message="test",
        reason="unfixable",
        api_key="secret",
        device_id="dev1",
    )
    assert calls[0][0] == "https://app.example/alerts"
    assert calls[0][1]["json"]["message"] == "test"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_iphone_notifier_custom_app(monkeypatch):
    calls = []

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResp()

    monkeypatch.setattr("aoa.notify.custom_app.httpx.post", fake_post)
    notifier = IPhoneNotifier(custom_app_webhook_url="https://app.example/alerts")
    channels = notifier.send(
        IPhoneNotification(
            title="AOA",
            message="Alert",
            reason=NotificationReason.NEEDS_VERIFICATION,
        )
    )
    assert channels == ["custom_app"]
    assert calls[0][1]["json"]["requires_response"] is True


def test_custom_app_webhook_missing_url():
    with pytest.raises(NotificationError, match="not set"):
        send_custom_app_webhook(
            "",
            title="t",
            message="m",
            reason="unfixable",
        )
