"""Expose brain mesh snippets for algorithm / analysis pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aoa.brain.store import BrainStore


def brain_context_for_algorithms(
    repo_root: Path | None = None,
    *,
    max_members: int = 12,
) -> dict[str, Any]:
    """Return a compact context dict injectable into Julie/Tom/swarm prompts."""
    store = BrainStore.open(repo_root)
    members = store.members[:max_members]
    algos = store.algorithms
    julie_feeds = []
    for m in members:
        if str(m.get("id")) == "julie":
            julie_feeds = list(m.get("feeds") or [])
            break
    return {
        "source": "aoa.brain",
        "mode": store.mode,
        "mesh_members": [
            {"name": m.get("name"), "role": m.get("role"), "feeds": m.get("feeds")}
            for m in members
        ],
        "algorithms": algos,
        "julie_feeds": julie_feeds,
        "spine_algorithms": "spine/Algorithms.md",
        "guidance": (
            "Use mesh owners when weighting algorithm clarity (Julie) and "
            "critical-only escalation (Kai). Prefer brain spine notes over ad-hoc memory."
        ),
    }


def format_brain_context_prompt(ctx: dict[str, Any] | None = None, *, repo_root: Path | None = None) -> str:
    """Flatten brain context into a short system-prompt addendum."""
    data = ctx or brain_context_for_algorithms(repo_root)
    lines = [
        "Second-brain mesh context:",
        f"- mode: {data.get('mode')}",
        f"- algorithms: {', '.join(str(a.get('id')) for a in (data.get('algorithms') or []))}",
        f"- julie_feeds: {', '.join(str(x) for x in (data.get('julie_feeds') or []))}",
        f"- guidance: {data.get('guidance')}",
    ]
    return "\n".join(lines)
