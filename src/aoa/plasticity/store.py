"""Plasticity store — load, inject, and consolidate cross-cycle memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aoa.journal.store import Journal
from aoa.plasticity.consolidate import consolidate
from aoa.plasticity.memory import PlasticMemory, load_memory, save_memory


class PlasticityStore:
    """Bridges the append-only journal and agent prompts across cycles."""

    def __init__(
        self,
        path: str | Path,
        journal: Journal,
        *,
        enabled: bool = True,
        tail: int = 200,
        max_lessons: int = 10,
    ) -> None:
        self.path = Path(path)
        self.journal = journal
        self.enabled = enabled
        self.tail = tail
        self.max_lessons = max_lessons
        self.memory = load_memory(self.path)

    def reload(self) -> PlasticMemory:
        self.memory = load_memory(self.path)
        return self.memory

    def prompt_block(self) -> str:
        if not self.enabled:
            return ""
        return self.memory.to_prompt_block()

    def consolidate(self) -> dict[str, Any]:
        """Distill recent journal events into memory and audit the update."""
        if not self.enabled:
            return {}

        before = self.memory.to_context()
        self.memory = consolidate(
            self.journal,
            self.memory,
            tail=self.tail,
            max_lessons=self.max_lessons,
        )
        save_memory(self.path, self.memory)
        delta = {
            "lessons": self.memory.lessons,
            "symbol_trust": self.memory.symbol_trust,
            "veto_counts": self.memory.veto_counts,
            "cycles_consolidated": self.memory.cycles_consolidated,
            "before_lessons": before.get("lessons", []),
        }
        self.journal.record("plasticity.update", delta)
        return delta
