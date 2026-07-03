"""A minimal append-only JSONL journal.

Every meaningful event — cycle start, signals, proposals, risk decisions, and
order submissions — is written as one JSON object per line. This gives a full,
replayable audit trail of what the swarm did and why, which is essential for any
system that can move real money.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, path: str | Path = "journal/aoa.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, payload: dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def tail(self, n: int = 20) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def load_daily_equity_baseline(self) -> tuple[str | None, float]:
        """Return persisted (ISO date, starting equity) for the daily-loss kill switch."""
        state_path = self.path.parent / "daily_equity.json"
        if not state_path.exists():
            return None, 0.0
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None, 0.0
        return data.get("date"), float(data.get("starting_equity", 0.0) or 0.0)

    def save_daily_equity_baseline(self, day, starting_equity: float) -> None:
        state_path = self.path.parent / "daily_equity.json"
        state_path.write_text(
            json.dumps({"date": day.isoformat(), "starting_equity": starting_equity}),
            encoding="utf-8",
        )
