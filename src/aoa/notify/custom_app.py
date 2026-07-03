"""Custom iPhone app notifications via your app's webhook backend.

Aaron POSTs a JSON payload to your server; your app backend forwards the alert
to the user's iPhone (typically via APNs). Never email.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


class NotificationError(RuntimeError):
    """Raised when a custom app notification could not be delivered."""


def build_custom_app_payload(
    *,
    title: str,
    message: str,
    reason: str,
    device_id: str = "",
) -> dict[str, Any]:
    """JSON body Aaron sends to your custom app webhook."""
    return {
        "source": "aoa-financial",
        "title": title,
        "message": message,
        "reason": reason,
        "requires_response": reason == "needs_verification",
        "priority": "high" if reason == "unfixable" else "normal",
        "device_id": device_id or None,
    }


def send_custom_app_webhook(
    webhook_url: str,
    *,
    title: str,
    message: str,
    reason: str,
    api_key: str = "",
    device_id: str = "",
    timeout: float = 15.0,
) -> None:
    """Deliver an alert to the user's custom iPhone app via its backend webhook."""
    url = webhook_url.strip()
    if not url:
        raise NotificationError("AOA_CUSTOM_APP_WEBHOOK_URL is not set.")

    payload = build_custom_app_payload(
        title=title,
        message=message,
        reason=reason,
        device_id=device_id,
    )
    headers = {"Content-Type": "application/json", "User-Agent": "AOA-Financial/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise NotificationError(f"Custom app webhook delivery failed: {exc}") from exc


def payload_preview(
    *,
    title: str,
    message: str,
    reason: str,
    device_id: str = "",
) -> str:
    """Human-readable JSON preview for debugging."""
    return json.dumps(
        build_custom_app_payload(
            title=title,
            message=message,
            reason=reason,
            device_id=device_id,
        ),
        indent=2,
    )
