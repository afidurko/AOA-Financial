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


def test_validate_rejects_bad_data_feed():
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        alpaca_data_feed="bad-feed",
    )
    problems = cfg.validate()
    assert any("ALPACA_DATA_FEED" in p for p in problems)


def test_validate_rejects_bad_bar_adjustment():
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        alpaca_bar_adjustment="bogus",
    )
    problems = cfg.validate()
    assert any("ALPACA_BAR_ADJUSTMENT" in p for p in problems)


def test_from_env_parses_alpaca_market_data_settings(monkeypatch):
    monkeypatch.setenv("ALPACA_DATA_FEED", "SIP")
    monkeypatch.setenv("ALPACA_BAR_ADJUSTMENT", "RAW")
    cfg = Config.from_env(load_dotenv=False)
    assert cfg.alpaca_data_feed == "sip"
    assert cfg.alpaca_bar_adjustment == "raw"


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


def test_from_env_bar_timeframes_default(monkeypatch):
    monkeypatch.delenv("AOA_BAR_TIMEFRAMES", raising=False)
    cfg = Config.from_env(load_dotenv=False)
    assert [t.key for t in cfg.bar_timeframes] == [
        "1Min",
        "3Min",
        "5Min",
        "15Min",
        "1Hour",
        "1Day",
        "12Month",
    ]


def test_from_env_bar_timeframes_override(monkeypatch):
    monkeypatch.setenv("AOA_BAR_TIMEFRAMES", "1Min,1Day,1Year")
    cfg = Config.from_env(load_dotenv=False)
    assert [t.key for t in cfg.bar_timeframes] == ["1Min", "1Day", "12Month"]


def test_validate_bar_feed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "k")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "s")
    monkeypatch.setenv("AOA_BAR_FEED", "bad")
    cfg = Config.from_env(load_dotenv=False)
    assert any("AOA_BAR_FEED" in p for p in cfg.validate())
