"""Tests for configuration parsing and validation."""

from __future__ import annotations

from aoa.config import Config


def test_trading_mode_paper_vs_live():
    paper = Config(alpaca_key_id="k", alpaca_secret_key="s", alpaca_live=False)
    assert paper.trading_mode == "paper"
    live = Config(alpaca_key_id="k", alpaca_secret_key="s", alpaca_live=True)
    assert live.trading_mode == "live"
    dry = Config(alpaca_live=True, dry_run=True)
    assert dry.trading_mode == "dry-run"


def test_validate_flags_missing_credentials():
    cfg = Config()
    problems = cfg.validate()
    assert any("ANTHROPIC_API_KEY" in p for p in problems)
    assert any("ALPACA" in p for p in problems)


def test_validate_clean_config():
    cfg = Config(anthropic_api_key="x", alpaca_key_id="k", alpaca_secret_key="s")
    assert cfg.validate() == []


def test_from_env_parses_universe(monkeypatch):
    monkeypatch.setenv("AOA_UNIVERSE", "aapl, msft ,nvda")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    cfg = Config.from_env(load_dotenv=False)
    assert cfg.universe == ("AAPL", "MSFT", "NVDA")


def test_from_env_risk_limits(monkeypatch):
    monkeypatch.setenv("AOA_MAX_POSITION_PCT", "0.25")
    monkeypatch.setenv("AOA_MAX_ORDERS_PER_CYCLE", "3")
    cfg = Config.from_env(load_dotenv=False)
    assert cfg.risk.max_position_pct == 0.25
    assert cfg.risk.max_orders_per_cycle == 3
