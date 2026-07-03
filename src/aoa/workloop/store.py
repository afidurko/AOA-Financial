"""Persist work-loop runs and append-only audit log."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.workloop.models import WorkloopRun


class WorkloopStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.log_path = self.root / "runs.jsonl"
        self.learnings_path = self.root / "learnings.json"
        self.approval_path = self.root / "approval.json"
        self.scheduler_path = self.root / "scheduler.json"

    def new_run_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def load_run(self) -> WorkloopRun | None:
        if not self.state_path.exists():
            return None
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not data.get("run_id"):
            return None
        return WorkloopRun.from_context(data)

    def save_run(self, run: WorkloopRun) -> None:
        self.state_path.write_text(
            json.dumps(run.to_context(), indent=2),
            encoding="utf-8",
        )

    def record(self, event: str, payload: dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()[-n:]
        out: list[dict[str, Any]] = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def load_learnings(self) -> dict[str, Any]:
        if not self.learnings_path.exists():
            return {"lessons": [], "adaptations": []}
        try:
            return json.loads(self.learnings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"lessons": [], "adaptations": []}

    def save_learnings(self, data: dict[str, Any]) -> None:
        self.learnings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_approval(self) -> dict[str, Any] | None:
        if not self.approval_path.exists():
            return None
        try:
            return json.loads(self.approval_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def save_approval(self, approval: dict[str, Any]) -> None:
        self.approval_path.write_text(json.dumps(approval, indent=2), encoding="utf-8")

    def clear_approval(self) -> None:
        if self.approval_path.exists():
            self.approval_path.unlink()

    def clear_run(self) -> None:
        if self.state_path.exists():
            self.state_path.unlink()

    def load_scheduler(self) -> dict[str, Any]:
        if not self.scheduler_path.exists():
            return {
                "iteration": 0,
                "last_completed_run_id": "",
                "last_completed_at": "",
                "next_run_at": "",
                "status": "idle",
            }
        try:
            data = json.loads(self.scheduler_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {
                "iteration": 0,
                "last_completed_run_id": "",
                "last_completed_at": "",
                "next_run_at": "",
                "status": "idle",
            }
        return {
            "iteration": int(data.get("iteration", 0) or 0),
            "last_completed_run_id": str(data.get("last_completed_run_id", "")),
            "last_completed_at": str(data.get("last_completed_at", "")),
            "next_run_at": str(data.get("next_run_at", "")),
            "status": str(data.get("status", "idle")),
        }

    def save_scheduler(self, data: dict[str, Any]) -> None:
        self.scheduler_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
