"""Tests for CLI helpers, exit codes, and offline doctor mode."""

from __future__ import annotations

from pathlib import Path

from aoa.cli import _cycle_exit_code, cmd_doctor, cmd_setup_moomoo
from aoa.config import Config
from aoa.execution.executor import ExecutionReport
from aoa.swarm.blackboard import Blackboard
from aoa.swarm.orchestrator import CycleResult


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


def test_doctor_reports_qm_url(monkeypatch, capsys):
    cfg = Config(
        anthropic_api_key="sk-test",
        alpaca_key_id="PKTEST",
        alpaca_secret_key="secret",
        qm_url="http://localhost:8081",
    )
    monkeypatch.setattr("aoa.cli.build_broker", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("aoa.cli.build_llm", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))

    code = cmd_doctor(cfg, offline=True)
    out = capsys.readouterr().out

    assert code == 0
    assert "QM harness link: http://localhost:8081" in out


def test_doctor_reports_visualhft_url(monkeypatch, capsys):
    cfg = Config(
        anthropic_api_key="sk-test",
        alpaca_key_id="PKTEST",
        alpaca_secret_key="secret",
        visualhft_url="https://github.com/afidurko/VisualHFT",
    )
    monkeypatch.setattr("aoa.cli.build_broker", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("aoa.cli.build_llm", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))

    code = cmd_doctor(cfg, offline=True)
    out = capsys.readouterr().out

    assert code == 0
    assert "VisualHFT link: https://github.com/afidurko/VisualHFT" in out


def test_cycle_exit_code_zero_on_success():
    result = CycleResult(
        blackboard=Blackboard(),
        execution=ExecutionReport(submitted=[object()], errors=[]),
    )
    assert _cycle_exit_code(result) == 0


def test_cycle_exit_code_one_on_execution_errors():
    result = CycleResult(
        blackboard=Blackboard(),
        execution=ExecutionReport(errors=[{"symbol": "AAPL", "error": "rejected"}]),
    )
    assert _cycle_exit_code(result) == 1


def test_doctor_offline_prints_package_version(monkeypatch, capsys):
    cfg = Config(anthropic_api_key="sk-test", alpaca_key_id="PKTEST", alpaca_secret_key="secret")
    monkeypatch.setattr("aoa.cli.build_broker", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("aoa.cli.build_llm", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("aoa.cli.package_version", lambda: "0.3.0")
    code = cmd_doctor(cfg, offline=True)
    out = capsys.readouterr().out
    assert code == 0
    assert "AOA Financial v0.3.0" in out


def test_cli_hftish_skips_env_template(tmp_path, monkeypatch, capsys):
    from aoa.cli import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("AOA_ENV=paper\n", encoding="utf-8")
    code = main(["hftish", "status", "--json"])
    assert code == 0
    assert not (tmp_path / ".env").exists()
    assert "example-hftish" in capsys.readouterr().out


def test_cmd_setup_moomoo_runs_helper(monkeypatch, capsys):
    cfg = Config(anthropic_api_key="sk-test", broker="moomoo")
    calls: list[list[str]] = []

    def fake_run(cmd, *, cwd, check):
        calls.append(cmd)
        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("aoa.cli.subprocess.run", fake_run)
    code = cmd_setup_moomoo(cfg)
    out = capsys.readouterr().out

    assert code == 0
    assert "Moomoo setup" in out
    assert calls
    assert calls[0][0] == "bash"
    assert calls[0][1].endswith("setup_moomoo_auth.sh")
    assert Path(calls[0][1]).name == "setup_moomoo_auth.sh"
