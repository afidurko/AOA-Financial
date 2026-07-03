"""Extract key data from discovered learning sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aoa.journal.store import Journal
from aoa.plasticity.memory import load_memory
from aoa.workloop.models import LearningSource


def extract_insights(
    sources: list[LearningSource],
    *,
    journal_path: Path,
    plasticity_path: Path,
    journal_tail: int = 100,
) -> dict[str, Any]:
    journal = Journal(journal_path)
    entries = journal.tail(journal_tail)
    events = [e.get("event", "") for e in entries]
    event_counts: dict[str, int] = {}
    for event in events:
        event_counts[event] = event_counts.get(event, 0) + 1

    vetoes = _collect_vetoes(entries)
    plasticity = load_memory(plasticity_path) if plasticity_path.exists() else None

    return {
        "source_count": len(sources),
        "source_kinds": sorted({s.kind for s in sources}),
        "journal_events": event_counts,
        "recent_vetoes": vetoes[:10],
        "plasticity_lessons": list(plasticity.lessons) if plasticity else [],
        "plasticity_trust": dict(plasticity.symbol_trust) if plasticity else {},
        "git_commits": _git_commits(sources),
        "test_files": _count_by_kind(sources, "tests"),
        "agent_modules": _count_by_kind(sources, "agents"),
    }


def _collect_vetoes(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    vetoes: list[dict[str, str]] = []
    for entry in entries:
        if entry.get("event") != "risk.review":
            continue
        for prop in entry.get("proposals", []):
            if prop.get("approved"):
                continue
            for note in prop.get("risk_notes", []):
                vetoes.append(
                    {
                        "symbol": str(prop.get("symbol", "")),
                        "note": str(note),
                        "ts": str(entry.get("ts", "")),
                    }
                )
    return vetoes


def _git_commits(sources: list[LearningSource]) -> list[str]:
    for source in sources:
        if source.kind == "git_history":
            raw = source.metadata.get("recent_commits", [])
            return [str(x) for x in raw]
    return []


def _count_by_kind(sources: list[LearningSource], kind: str) -> int:
    for source in sources:
        if source.kind == kind:
            return int(source.metadata.get("file_count", 0))
    return 0
