"""Swarm event bus — auditable stage and domain notifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class SwarmEvent:
    """One event emitted during a cycle (stage transitions, domain writes, …)."""

    kind: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_context(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "payload": self.payload,
            "ts": self.ts,
        }


EventHandler = Callable[[SwarmEvent], None]


class EventBus:
    """Lightweight pub/sub for intra-cycle coordination and auditing."""

    def __init__(self) -> None:
        self._events: list[SwarmEvent] = []
        self._handlers: dict[str, list[EventHandler]] = {}

    @property
    def events(self) -> list[SwarmEvent]:
        return list(self._events)

    def subscribe(self, kind: str, handler: EventHandler) -> None:
        self._handlers.setdefault(kind, []).append(handler)

    def emit(self, kind: str, source: str, payload: dict[str, Any] | None = None) -> SwarmEvent:
        event = SwarmEvent(kind=kind, source=source, payload=dict(payload or {}))
        self._events.append(event)
        for handler in self._handlers.get(kind, []):
            handler(event)
        for handler in self._handlers.get("*", []):
            handler(event)
        return event

    def of_kind(self, kind: str) -> list[SwarmEvent]:
        return [e for e in self._events if e.kind == kind]
