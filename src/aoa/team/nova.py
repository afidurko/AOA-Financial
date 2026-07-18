"""Nova — second-brain / knowledge mesh curator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aoa.agents.base import Agent
from aoa.brain.store import BrainStore


class NovaAgent(Agent):
    name = "nova"
    display_name = "Nova"
    role = "Second-Brain / Knowledge Mesh Curator"

    system_prompt = (
        "You are Nova, curator of the AOA second-brain workspace (brain/). "
        "You keep the mesh graph accurate, sync spines with vault mirrors, and "
        "ensure algorithms can read durable knowledge. You do not trade or merge code."
    )

    def sync_brain(self, repo_root: Path | None = None) -> dict[str, Any]:
        store = BrainStore.open(repo_root)
        stats = store.stats()
        path = store.write_capture(
            "Nova brain sync",
            f"Mesh sync complete.\n\n```json\n{stats}\n```",
        )
        return {
            "agent": self.display_name,
            "role": self.role,
            "ok": stats.get("required_ok", False),
            "stats": stats,
            "capture": str(path),
            "context": store.to_context(),
        }
