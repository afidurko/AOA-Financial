"""Tests for workloop verify helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from aoa.workloop.verify import run_verify


def test_run_verify_uses_python_module_invocation(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))

        class _Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return _Result()

    monkeypatch.setattr("aoa.workloop.verify.subprocess.run", fake_run)
    repo = Path(__file__).resolve().parents[1]
    result = run_verify(repo, mode="full")

    assert result["passed"] is True
    assert len(calls) == 2
    assert calls[0][:3] == [sys.executable, "-m", "ruff"]
    assert calls[1][:3] == [sys.executable, "-m", "pytest"]


def test_run_verify_quick_skips_pytest(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))

        class _Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return _Result()

    monkeypatch.setattr("aoa.workloop.verify.subprocess.run", fake_run)
    result = run_verify(Path.cwd(), mode="quick")

    assert result["passed"] is True
    assert result["mode"] == "quick"
    assert len(calls) == 1
    assert calls[0][:3] == [sys.executable, "-m", "ruff"]
    assert result["pytest"]["ok"] is True
    assert "skipped" in result["pytest"]["cmd"]
