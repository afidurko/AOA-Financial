"""Tests for the optional hftbacktest integration."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from aoa.cli import cmd_hft_smoke, cmd_hft_status
from aoa.hftbacktest import HAS_HFTBACKTEST, probe_status

pytestmark_hft = pytest.mark.skipif(
    not HAS_HFTBACKTEST, reason="hftbacktest extra not installed"
)


def test_probe_status_shape():
    status = probe_status()
    assert "installed" in status
    assert "upstream" in status
    assert status["offline_only"] is True
    assert status["installed"] is HAS_HFTBACKTEST
    if HAS_HFTBACKTEST:
        assert status["version"]
        assert status["engine"]


def test_cli_hft_status_help():
    proc = subprocess.run(
        [sys.executable, "-m", "aoa.cli", "hft", "status", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--json" in proc.stdout


def test_cmd_hft_status_json(capsys):
    code = cmd_hft_status(as_json=True)
    out = json.loads(capsys.readouterr().out)
    assert out["offline_only"] is True
    assert out["installed"] is HAS_HFTBACKTEST
    assert code == (0 if HAS_HFTBACKTEST else 1)


@pytestmark_hft
def test_synthetic_smoke_ok():
    from aoa.hftbacktest import run_npz_smoke

    result = run_npz_smoke(n_events=100, steps=10, seed=7)
    assert result.ok
    assert result.steps > 0
    assert result.best_bid is not None and result.best_bid > 0
    assert result.best_ask is not None and result.best_ask > result.best_bid
    assert result.position == 0.0
    payload = result.to_dict()
    assert payload["ok"] is True


@pytestmark_hft
def test_cmd_hft_smoke_json(capsys):
    code = cmd_hft_smoke(n_events=80, steps=5, seed=3, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["ok"] is True
    assert data["steps"] >= 1


@pytestmark_hft
def test_make_synthetic_rejects_tiny_tape():
    from aoa.hftbacktest.synthetic import make_synthetic_l2_tape

    with pytest.raises(ValueError):
        make_synthetic_l2_tape(n_events=2)
