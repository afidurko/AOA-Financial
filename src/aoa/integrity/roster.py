"""Integrity Ten — cohesive unit for code, workspace, neural memory, and mesh checks.

Drawn from the twelve-member ATTL roster (excludes Tom & Morgan market lanes).
Each member owns a distinct integrity domain; edges stay in brain/mesh/index.yaml.
"""

from __future__ import annotations

from typing import NamedTuple


class IntegrityRole(NamedTuple):
    name: str
    role: str
    slug: str
    domain: str


# Stable order for Aaron BRIEF / integrity reports.
INTEGRITY_TEN: tuple[IntegrityRole, ...] = (
    IntegrityRole(
        "Julie",
        "Algorithm & Code Clarity Integrity",
        "julie",
        "algorithms",
    ),
    IntegrityRole(
        "Hailey",
        "Docs & Companion Mesh Integrity",
        "hailey",
        "docs",
    ),
    IntegrityRole(
        "Alan",
        "Mesh Cohesion Aggregator",
        "alan",
        "cohesion",
    ),
    IntegrityRole(
        "Andrea",
        "Hard Safety Floor Integrity",
        "andrea",
        "safety",
    ),
    IntegrityRole(
        "Bob",
        "Code & Systems Integrity",
        "bob",
        "code",
    ),
    IntegrityRole(
        "Aaron",
        "Corrective Notification Lead",
        "aaron",
        "notify",
    ),
    IntegrityRole(
        "Alex",
        "Approval BRIEF Router",
        "alex",
        "approvals",
    ),
    IntegrityRole(
        "Nova",
        "Neural Memory & Workspace Mesh",
        "nova",
        "neural_memory",
    ),
    IntegrityRole(
        "Reed",
        "Corrective Implementer",
        "reed",
        "fix",
    ),
    IntegrityRole(
        "Kai",
        "Critical Integrity Sentinel",
        "kai",
        "critical",
    ),
)


def integrity_names() -> list[str]:
    return [m.name for m in INTEGRITY_TEN]


def integrity_pairs() -> list[tuple[str, str]]:
    return [(m.name, m.role) for m in INTEGRITY_TEN]


def integrity_domains() -> dict[str, str]:
    return {m.slug: m.domain for m in INTEGRITY_TEN}
