"""Tests for workloop dependency upgrade pipeline."""

from __future__ import annotations

from unittest.mock import patch

from aoa.workloop.upgrade import run_upgrade_pipeline


def test_upgrade_pipeline_dry_run_uses_full_verify():
    verify_ok = {
        "passed": True,
        "mode": "full",
        "ruff": {"ok": True},
        "pytest": {"ok": True},
    }
    with patch("aoa.workloop.upgrade.run_verify", return_value=verify_ok) as mock_verify:
        result = run_upgrade_pipeline(dry_run=True)
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["phase"] == "dry-run"
    assert result["upgrade"]["message"] == "Dry-run: upgrade skipped."
    mock_verify.assert_called_once()
    assert mock_verify.call_args.kwargs.get("mode") == "full"


def test_upgrade_pipeline_fails_on_baseline():
    with patch(
        "aoa.workloop.upgrade.run_verify",
        return_value={"passed": False, "mode": "full", "ruff": {"ok": False}},
    ) as mock_verify:
        result = run_upgrade_pipeline(dry_run=False)
    assert result["ok"] is False
    assert result["phase"] == "baseline-verify"
    assert mock_verify.call_args.kwargs.get("mode") == "full"


def test_upgrade_pipeline_dry_run_skips_pip():
    verify_ok = {
        "passed": True,
        "mode": "full",
        "ruff": {"ok": True},
        "pytest": {"ok": True},
    }
    with patch("aoa.workloop.upgrade.run_verify", return_value=verify_ok):
        with patch("aoa.workloop.upgrade.run_upgrade") as upgrade:
            result = run_upgrade_pipeline(dry_run=True)
    assert result["ok"] is True
    upgrade.assert_not_called()


def test_upgrade_pipeline_runs_pip_then_reverify():
    verify_ok = {
        "passed": True,
        "mode": "full",
        "ruff": {"ok": True},
        "pytest": {"ok": True},
    }
    upgrade_ok = {"ok": True, "returncode": 0, "output": ""}
    with patch("aoa.workloop.upgrade.run_verify", return_value=verify_ok):
        with patch("aoa.workloop.upgrade.run_upgrade", return_value=upgrade_ok):
            result = run_upgrade_pipeline(dry_run=False)
    assert result["ok"] is True
    assert result["phase"] == "complete"
    assert result["upgrade"]["ok"] is True

