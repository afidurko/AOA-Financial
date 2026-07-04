"""Persist repair-loop queue and run history."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.repair.models import RepairItem


class RepairStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.queue_path = self.root / "queue.json"
        self.log_path = self.root / "runs.jsonl"

    def new_run_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def load_queue(self) -> list[RepairItem]:
        if not self.queue_path.exists():
            return []
        try:
            data = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [RepairItem.from_context(row) for row in data.get("items", [])]

    def save_queue(self, items: list[RepairItem]) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": [i.to_context() for i in items],
        }
        self.queue_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record(self, event: str, payload: dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
