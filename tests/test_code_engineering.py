"""Tests for coding-engineer checks owned by Bob, Julie, and Alan."""

from __future__ import annotations

from aoa.team.code_engineering import run_code_quality_audit
from aoa.team.models import HealthStatus


def test_code_quality_audit_passes_in_repo():
    report = run_code_quality_audit()
    assert report.can_proceed is True
    assert report.worst_status is HealthStatus.OK
    areas = {f.area for f in report.findings}
    assert "pricing" in areas
    assert "web_app" in areas
    assert "pipeline" in areas
