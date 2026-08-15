"""Tests for CLI helpers, exit codes, and offline doctor mode."""

from __future__ import annotations

from pathlib import Path

from aoa.cli import _cycle_exit_code, _repo_root, cmd_doctor, cmd_setup_moomoo
from aoa.config import Config
from aoa.execution.executor import ExecutionReport
from aoa.swarm.blackboard import Blackboard
from aoa.swarm.orchestrator import CycleResult


def test_doctor_offline_skips_connectivity(monkeypatch, capsys):
    cfg = Config(
        broker="moomoo",
        llm_provider="openai_compatible",
        llm_base_url="http://127.0.0.1:8000/v1",
    )

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("broker should not be called in offline mode")

    monkeypatch.setattr("aoa.cli.build_broker", _fail_if_called)
    monkeypatch.setattr("aoa.cli.build_llm", _fail_if_called)

    code = cmd_doctor(cfg, offline=True)
    out = capsys.readouterr().out

    assert code == 0
    assert "Offline mode" in out
    assert "Broker: moomoo" in out


def test_doctor_moomoo_skips_alpaca_crypto(monkeypatch, capsys):
    """Moomoo doctor must not require Alpaca crypto/keys — OpenD + WASTE only."""
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    from aoa.brokerage.models import Account, Bar

    cfg = Config(
        broker="moomoo",
        llm_provider="openai_compatible",
        llm_base_url="http://127.0.0.1:8000/v1",
        model="kimi-linear",
    )

    def _no_alpaca(*args, **kwargs):
        raise AssertionError("AlpacaBarsFetcher must not run for Moomoo doctor")

    monkeypatch.setattr("aoa.cli.AlpacaBarsFetcher", _no_alpaca)

    broker = MagicMock()
    broker.name = "moomoo-paper"
    broker.get_account.return_value = Account(
        equity=100_000.0,
        cash=100_000.0,
        settled_cash=100_000.0,
        buying_power=100_000.0,
        options_level=0,
    )
    broker.verify_stock_bars.return_value = Bar(
        timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
        open=1.0,
        high=1.0,
        low=1.0,
        close=500.0,
        volume=1.0,
    )
    monkeypatch.setattr("aoa.cli.build_broker", lambda _cfg: broker)

    llm = MagicMock()
    monkeypatch.setattr("aoa.cli.build_llm", lambda _cfg: llm)

    code = cmd_doctor(cfg, offline=False)
    out = capsys.readouterr().out

    assert code == 0
    assert "Broker reachable (moomoo-paper)" in out
    assert "openai_compatible" in out
    assert "Crypto bars" not in out
    llm.ping.assert_called_once()


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


def test_repo_root_finds_pyproject():
    root = _repo_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "aoa").is_dir()


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
