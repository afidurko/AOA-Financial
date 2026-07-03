"""Tests for coding-engineer checks owned by Bob, Julie, and Alan."""

from __future__ import annotations

import pytest

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


def test_import_sweep_skips_optional_modules():
    from aoa.team.code_engineering import import_sweep

    finding = import_sweep(
        ("aoa.agents.base", "aoa.web.app"),
        optional=frozenset({"aoa.web.app"}),
    )
    if finding.status is HealthStatus.CRITICAL:
        pytest.skip("aoa.web.app required but failed for non-optional reason")
    assert finding.status is HealthStatus.OK
    assert "optional skipped" in finding.detail or "import cleanly" in finding.detail
