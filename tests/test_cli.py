"""Tests for CLI helpers and offline doctor mode."""

from __future__ import annotations

from aoa.cli import cmd_doctor
from aoa.config import Config


def test_doctor_offline_skips_connectivity(monkeypatch, capsys):
    cfg = Config(
        anthropic_api_key="sk-test",
        alpaca_key_id="PKTEST",
        alpaca_secret_key="secret",
    )

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("broker should not be called in offline mode")

    monkeypatch.setattr("aoa.cli.build_broker", _fail_if_called)
    monkeypatch.setattr("aoa.cli.build_llm", _fail_if_called)

    code = cmd_doctor(cfg, offline=True)
    out = capsys.readouterr().out

    assert code == 0
    assert "Offline mode" in out
