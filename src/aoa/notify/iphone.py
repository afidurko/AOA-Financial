"""iPhone push notifications for Aaron (CEO alerts).

Deliveries go to the user's iPhone via a custom app webhook, Pushover, or ntfy —
never email.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import httpx

from aoa.notify.custom_app import send_custom_app_webhook, send_structured_webhook
from aoa.notify.types import StructuredNotification

if TYPE_CHECKING:
    from aoa.config import Config


def _ascii_header(value: str) -> str:
    """ntfy HTTP headers must be ASCII."""
    return value.encode("ascii", "replace").decode("ascii")


def webhook_is_usable(url: str) -> bool:
    """True when the custom-app URL looks real (not an .env.example placeholder)."""
    u = (url or "").strip().lower()
    if not u.startswith("http"):
        return False
    if "example.com" in u or "your-server" in u:
        return False
    return True


class NotificationError(RuntimeError):
    """Raised when an iPhone push could not be delivered."""


class NotificationReason(str, Enum):
    UNFIXABLE = "unfixable"
    NEEDS_VERIFICATION = "needs_verification"
    INFORM = "inform"


@dataclass(frozen=True)
class IPhoneNotification:
    title: str
    message: str
    reason: NotificationReason


class IPhoneNotifier:
    """Send push alerts to the user's iPhone."""

    def __init__(
        self,
        *,
        custom_app_webhook_url: str = "",
        custom_app_api_key: str = "",
        custom_app_device_id: str = "",
        pushover_user_key: str = "",
        pushover_app_token: str = "",
        ntfy_topic: str = "",
        ntfy_server: str = "https://ntfy.sh",
    ) -> None:
        self.custom_app_webhook_url = custom_app_webhook_url.strip()
        self.custom_app_api_key = custom_app_api_key.strip()
        self.custom_app_device_id = custom_app_device_id.strip()
        self.pushover_user_key = pushover_user_key.strip()
        self.pushover_app_token = pushover_app_token.strip()
        self.ntfy_topic = ntfy_topic.strip()
        self.ntfy_server = ntfy_server.rstrip("/")

    @classmethod
    def from_config(cls, config: Config) -> IPhoneNotifier:
        return cls(
            custom_app_webhook_url=config.custom_app_webhook_url,
            custom_app_api_key=config.custom_app_api_key,
            custom_app_device_id=config.custom_app_device_id,
            pushover_user_key=config.pushover_user_key,
            pushover_app_token=config.pushover_app_token,
            ntfy_topic=config.ntfy_topic,
            ntfy_server=config.ntfy_server,
        )

    @property
    def configured(self) -> bool:
        return bool(self.channel_names())

    def channel_names(self) -> list[str]:
        """Names of channels that would actually receive a push."""
        names: list[str] = []
        if webhook_is_usable(self.custom_app_webhook_url):
            names.append("custom_app")
        if self.pushover_user_key and self.pushover_app_token:
            names.append("pushover")
        if self.ntfy_topic:
            names.append("ntfy")
        return names

    @property
    def uses_custom_app(self) -> bool:
        return webhook_is_usable(self.custom_app_webhook_url)

    def status(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "channels": self.channel_names(),
            "custom_app": self.uses_custom_app,
            "pushover": bool(self.pushover_user_key and self.pushover_app_token),
            "ntfy": bool(self.ntfy_topic),
            "ntfy_topic": self.ntfy_topic or None,
            "ntfy_server": self.ntfy_server if self.ntfy_topic else None,
            "setup_hint": (
                None
                if self.configured
                else (
                    "Set AOA_NTFY_TOPIC (easiest), or Pushover keys, "
                    "or a real AOA_CUSTOM_APP_WEBHOOK_URL (not example.com)."
                )
            ),
        }

    def send(self, notification: IPhoneNotification) -> list[str]:
        """Deliver to every configured iPhone channel. Returns channel names used."""
        if not self.configured:
            raise NotificationError(
                "iPhone push is not configured. Set AOA_CUSTOM_APP_WEBHOOK_URL for your "
                "custom app, or Pushover (AOA_PUSHOVER_USER_KEY + AOA_PUSHOVER_APP_TOKEN) "
                "or ntfy (AOA_NTFY_TOPIC)."
            )
        delivered: list[str] = []
        if self.uses_custom_app:
            self._send_custom_app(notification)
            delivered.append("custom_app")
        if self.pushover_user_key and self.pushover_app_token:
            self._send_pushover(notification)
            delivered.append("pushover")
        if self.ntfy_topic:
            self._send_ntfy(notification)
            delivered.append("ntfy")
        return delivered

    def send_structured(self, notification: StructuredNotification) -> list[str]:
        """Deliver a structured trading/analysis alert to every usable channel."""
        if not self.configured:
            raise NotificationError("iPhone push is not configured.")
        delivered: list[str] = []
        if self.uses_custom_app:
            send_structured_webhook(
                self.custom_app_webhook_url,
                notification,
                api_key=self.custom_app_api_key,
                device_id=self.custom_app_device_id,
            )
            delivered.append("custom_app")
        legacy = IPhoneNotification(
            title=notification.concise_title(),
            message=notification.message,
            reason=(
                NotificationReason.NEEDS_VERIFICATION
                if notification.requires_response
                else NotificationReason.INFORM
            ),
        )
        if self.pushover_user_key and self.pushover_app_token:
            self._send_pushover(legacy)
            delivered.append("pushover")
        if self.ntfy_topic:
            self._send_ntfy(legacy)
            delivered.append("ntfy")
        return delivered

    def _send_custom_app(self, notification: IPhoneNotification) -> None:
        try:
            send_custom_app_webhook(
                self.custom_app_webhook_url,
                title=notification.title,
                message=notification.message,
                reason=notification.reason.value,
                api_key=self.custom_app_api_key,
                device_id=self.custom_app_device_id,
            )
        except Exception as exc:
            raise NotificationError(str(exc)) from exc

    def _send_pushover(self, notification: IPhoneNotification) -> None:
        priority = (
            1
            if notification.reason is NotificationReason.UNFIXABLE
            else 0
        )
        try:
            resp = httpx.post(
                "https://api.pushover.net/1/messages.json",
                data={
                    "token": self.pushover_app_token,
                    "user": self.pushover_user_key,
                    "title": notification.title,
                    "message": notification.message,
                    "priority": priority,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise NotificationError(f"Pushover delivery failed: {exc}") from exc

    def _send_ntfy(self, notification: IPhoneNotification) -> None:
        headers = {
            "Title": _ascii_header(notification.title),
            "Tags": notification.reason.value,
        }
        if notification.reason is NotificationReason.UNFIXABLE:
            headers["Priority"] = "high"
        if notification.reason is NotificationReason.NEEDS_VERIFICATION:
            headers["Priority"] = "default"
            headers["Tags"] = "warning,needs_verification"
        try:
            resp = httpx.post(
                f"{self.ntfy_server}/{self.ntfy_topic}",
                content=notification.message.encode("utf-8"),
                headers=headers,
                timeout=15.0,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise NotificationError(f"ntfy delivery failed: {exc}") from exc
