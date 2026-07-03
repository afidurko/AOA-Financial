"""Durable plastic memory — lessons and symbol trust scores."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class PlasticMemory:
    """Cross-cycle memory distilled from journal events."""

    lessons: list[str] = field(default_factory=list)
    symbol_trust: dict[str, float] = field(default_factory=dict)
    veto_counts: dict[str, int] = field(default_factory=dict)
    cycles_consolidated: int = 0
    updated_at: str = ""

    def to_context(self) -> dict[str, Any]:
        return {
            "lessons": list(self.lessons),
            "symbol_trust": dict(self.symbol_trust),
            "veto_counts": dict(self.veto_counts),
            "cycles_consolidated": self.cycles_consolidated,
            "updated_at": self.updated_at,
        }

    def to_prompt_block(self) -> str:
        """Render memory as an LLM-facing context block."""
        if not self.lessons and not self._notable_trust():
            return ""

        lines = [
            "Persistent lessons from recent cycles "
            "(use as bias when sizing and selecting trades, not as hard rules):"
        ]
        for lesson in self.lessons:
            lines.append(f"- {lesson}")

        notable = self._notable_trust()
        if notable:
            lines.append(
                "Symbol trust scores (-1.0 = be cautious, +1.0 = historically favorable):"
            )
            for sym, score in notable:
                lines.append(f"- {sym}: {score:+.2f}")

        return "\n".join(lines)

    def _notable_trust(self) -> list[tuple[str, float]]:
        rows = [(sym, score) for sym, score in self.symbol_trust.items() if abs(score) >= 0.1]
        rows.sort(key=lambda row: abs(row[1]), reverse=True)
        return rows[:8]


def load_memory(path: Path) -> PlasticMemory:
    if not path.exists():
        return PlasticMemory()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return PlasticMemory()
    return PlasticMemory(
        lessons=[str(x) for x in data.get("lessons", [])],
        symbol_trust={str(k): float(v) for k, v in data.get("symbol_trust", {}).items()},
        veto_counts={str(k): int(v) for k, v in data.get("veto_counts", {}).items()},
        cycles_consolidated=int(data.get("cycles_consolidated", 0) or 0),
        updated_at=str(data.get("updated_at", "")),
    )


def save_memory(path: Path, memory: PlasticMemory) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory.to_context(), indent=2), encoding="utf-8")


def touch_memory(memory: PlasticMemory) -> None:
    memory.updated_at = datetime.now(timezone.utc).isoformat()
