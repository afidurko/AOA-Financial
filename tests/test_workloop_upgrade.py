"""Tests for workloop dependency upgrade pipeline."""

from __future__ import annotations

from unittest.mock import patch

from aoa.workloop.upgrade import run_upgrade_pipeline


def test_upgrade_pipeline_dry_run_skips_pip():
    verify_ok = {"passed": True, "ruff": {"ok": True}, "pytest": {"ok": True}}
    with patch("aoa.workloop.upgrade.run_verify", return_value=verify_ok):
        result = run_upgrade_pipeline(dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["upgrade"]["message"] == "Dry-run: upgrade skipped."


def test_upgrade_pipeline_fails_on_baseline():
    with patch(
        "aoa.workloop.upgrade.run_verify",
        return_value={"passed": False, "ruff": {"ok": False}},
    ):
        result = run_upgrade_pipeline(dry_run=False)
    assert result["ok"] is False
    assert result["phase"] == "baseline-verify"
