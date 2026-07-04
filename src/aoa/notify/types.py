"""Structured notification types for trading alerts and approvals."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NotificationKind(str, Enum):
    OPPORTUNITY = "opportunity"
    ANALYSIS = "analysis"
    ALERT = "alert"
    APPROVAL = "approval"
    ESCALATION = "escalation"


@dataclass(frozen=True)
class StructuredNotification:
    kind: NotificationKind
    title: str
    message: str
    symbol: str = ""
    conviction: float | None = None
    volume_ratio: float | None = None
    notional: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    journal_event: str = ""
    requires_response: bool = False
    priority: str = "normal"

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": "aoa-financial",
            "kind": self.kind.value,
            "title": self.title,
            "message": self.message,
            "symbol": self.symbol or None,
            "conviction": self.conviction,
            "volume_ratio": self.volume_ratio,
            "notional": self.notional,
            "metrics": self.metrics,
            "run_id": self.run_id or None,
            "journal_event": self.journal_event or None,
            "requires_response": self.requires_response,
            "priority": self.priority,
            "reason": "needs_verification" if self.requires_response else "normal",
        }

    def concise_title(self) -> str:
        if self.symbol and self.conviction is not None:
            parts = [self.symbol, f"{self.conviction:.0%}" if self.conviction <= 1 else f"{self.conviction:.0f}%"]
            if self.volume_ratio is not None:
                parts.append(f"Vol {self.volume_ratio:.1f}x")
            return " · ".join(parts)
        return self.title
