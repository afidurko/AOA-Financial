"""Canonical twelve-member meshed team roster."""

from __future__ import annotations

from typing import NamedTuple


class TeamRole(NamedTuple):
    name: str
    role: str
    slug: str


# Order is stable for Aaron CEO reports and ATTL mesh.
TWELVE_MEMBER_ROSTER: tuple[TeamRole, ...] = (
    TeamRole("Tom", "Trend Analyst", "tom"),
    TeamRole("Julie", "Algorithm Specialist & Code Clarity", "julie"),
    TeamRole("Morgan", "Market & Volume Analyst", "morgan"),
    TeamRole("Hailey", "News & Catalyst Analyst", "hailey"),
    TeamRole("Alan", "Decision Aggregator & Code Oversight", "alan"),
    TeamRole("Andrea", "Risk Manager & Pre-Execution", "andrea"),
    TeamRole("Bob", "Systems Health & Code Integrity", "bob"),
    TeamRole("Aaron", "CEO", "aaron"),
    TeamRole("Alex", "Executive Assistant", "alex"),
    TeamRole("Nova", "Second-Brain / Knowledge Mesh Curator", "nova"),
    TeamRole("Reed", "Task-Loop Architect & Implementer", "reed"),
    TeamRole("Kai", "Critical Failure Sentinel", "kai"),
)


def roster_pairs() -> list[tuple[str, str]]:
    """(name, role) pairs for Aaron _ensure_roster compatibility."""
    return [(m.name, m.role) for m in TWELVE_MEMBER_ROSTER]


def roster_names() -> list[str]:
    return [m.name for m in TWELVE_MEMBER_ROSTER]
