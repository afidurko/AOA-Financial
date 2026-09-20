"""A minimal append-only JSONL journal.

Every meaningful event — cycle start, signals, proposals, risk decisions, and
order submissions — is written as one JSON object per line. This gives a full,
replayable audit trail of what the swarm did and why, which is essential for any
system that can move real money.

Agents and sub-agents record from worker threads, so appends are serialized
with a lock: one event is always one intact line.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, path: str | Path = "journal/aoa.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, event: str, payload: dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        line = json.dumps(entry, default=str) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    def tail(self, n: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        return _parse_lines(self.path.read_text(encoding="utf-8").splitlines()[-n:])

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return _parse_lines(self.path.read_text(encoding="utf-8").splitlines())


def _parse_lines(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
