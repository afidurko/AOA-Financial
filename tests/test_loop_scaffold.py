"""Smoke tests for loop-engineering scaffold consistency."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

LOOP_FILES = (
    "LOOP.md",
    "STATE.md",
    "loop-constraints.md",
    "loop-run-log.md",
    "loop-budget.md",
)

LOOP_SKILLS = (
    "loop-constraints",
    "loop-budget",
    "loop-triage",
    "minimal-fix",
    "loop-verifier",
)


@pytest.mark.parametrize("filename", LOOP_FILES)
def test_loop_file_exists(filename: str) -> None:
    path = REPO_ROOT / filename
    assert path.is_file(), f"Missing loop file: {filename}"
    assert path.stat().st_size > 0, f"Empty loop file: {filename}"


@pytest.mark.parametrize("skill_name", LOOP_SKILLS)
def test_loop_skill_exists(skill_name: str) -> None:
    skill_path = REPO_ROOT / ".cursor" / "skills" / skill_name / "SKILL.md"
    assert skill_path.is_file(), f"Missing loop skill: {skill_name}"


def test_loop_md_references_documented_skills() -> None:
    loop_md = (REPO_ROOT / "LOOP.md").read_text(encoding="utf-8")
    for skill_name in LOOP_SKILLS:
        assert skill_name in loop_md, f"LOOP.md should reference skill: {skill_name}"


def test_code_audit_includes_loop_scaffold_check() -> None:
    from aoa.team.code_engineering import run_code_quality_audit
    from aoa.team.models import HealthStatus

    report = run_code_quality_audit(repo_root=REPO_ROOT)
    areas = {f.area: f for f in report.findings}
    assert "loop_scaffold" in areas
    assert areas["loop_scaffold"].status is HealthStatus.OK
