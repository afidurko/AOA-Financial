"""Tests for configuration parsing and validation."""

from __future__ import annotations

from pathlib import Path

from aoa.config import (
    Config,
    data_dir_for,
    journal_path_for,
    load_env_files,
)


def test_trading_mode_paper_vs_live():
    paper = Config(
        broker="alpaca",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        alpaca_live=False,
    )
    assert paper.trading_mode == "paper"
    live = Config(
        broker="alpaca",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        alpaca_live=True,
    )
    assert live.trading_mode == "live"
    dry = Config(broker="moomoo", moomoo_live=True, dry_run=True)
    assert dry.trading_mode == "dry-run"
    moomoo_paper = Config(broker="moomoo", moomoo_live=False)
    assert moomoo_paper.trading_mode == "paper"


def test_validate_flags_missing_credentials():
    cfg = Config(env="paper-dry", broker="moomoo")
    problems = cfg.validate()
    assert any("ANTHROPIC_API_KEY" in p for p in problems)
    assert not any("ALPACA" in p for p in problems)


def test_validate_alpaca_broker_requires_keys():
    cfg = Config(env="paper-dry", broker="alpaca")
    problems = cfg.validate()
    assert any("ALPACA" in p for p in problems)


def test_validate_test_env_skips_external_credentials():
    cfg = Config(env="test")
    assert cfg.validate() == []


def test_validate_clean_config():
    cfg = Config(
        env="paper-dry",
        broker="moomoo",
        anthropic_api_key="x",
    )
    assert cfg.validate() == []


def test_validate_clean_config_alpaca():
    cfg = Config(
        env="paper-dry",
        broker="alpaca",
        anthropic_api_key="x",
        alpaca_key_id="k",
        alpaca_secret_key="s",
    )
    assert cfg.validate() == []


def test_has_brokerage_creds_accepts_oauth():
    cfg = Config(alpaca_oauth_token="oauth-token")
    assert cfg.has_brokerage_creds is True


def test_from_env_loads_alpaca_cli_oauth_profile(tmp_path, monkeypatch):
    config_dir = tmp_path / "alpaca"
    profiles = config_dir / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "paper.yaml").write_text(
        'access_token: "cli-oauth-token"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ALPACA_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    cfg = Config.from_env(load_dotenv=False)
    assert cfg.alpaca_oauth_token == "cli-oauth-token"
    assert cfg.alpaca_auth_source == "cli-oauth"
    assert cfg.has_brokerage_creds is True


def test_validate_rejects_bad_effort():
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        effort="turbo",
    )
    problems = cfg.validate()
    assert any("AOA_EFFORT" in p for p in problems)


def test_validate_rejects_bad_data_feed():
    cfg = Config(
        broker="alpaca",
        anthropic_api_key="x",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        alpaca_data_feed="bad-feed",
    )
    problems = cfg.validate()
    assert any("ALPACA_DATA_FEED" in p for p in problems)


def test_validate_rejects_bad_bar_adjustment():
    cfg = Config(
        broker="alpaca",
        anthropic_api_key="x",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        alpaca_bar_adjustment="bogus",
    )
    problems = cfg.validate()
    assert any("ALPACA_BAR_ADJUSTMENT" in p for p in problems)


def test_validate_live_requires_acknowledgement():
    cfg = Config(
        env="live",
        anthropic_api_key="x",
        alpaca_key_id="k",
        alpaca_secret_key="s",
        alpaca_live=True,
        live_acknowledged=False,
    )
    problems = cfg.validate()
    assert any("AOA_LIVE_ACK" in p for p in problems)


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


def test_env_defaults_for_paper_dry(monkeypatch):
    monkeypatch.delenv("AOA_DRY_RUN", raising=False)
    monkeypatch.delenv("ALPACA_LIVE", raising=False)
    monkeypatch.setenv("AOA_ENV", "paper-dry")
    cfg = Config.from_env(load_dotenv=False)
    assert cfg.dry_run is True
    assert cfg.alpaca_live is False


def test_env_defaults_for_paper_live_orders(monkeypatch):
    monkeypatch.delenv("AOA_DRY_RUN", raising=False)
    monkeypatch.delenv("ALPACA_LIVE", raising=False)
    monkeypatch.setenv("AOA_ENV", "paper")
    cfg = Config.from_env(load_dotenv=False)
    assert cfg.dry_run is False
    assert cfg.alpaca_live is False


def test_journal_path_is_scoped_by_env(monkeypatch):
    monkeypatch.setenv("AOA_ENV", "paper-dry")
    cfg = Config.from_env(load_dotenv=False)
    assert cfg.journal_path == journal_path_for("paper-dry")
    assert cfg.data_dir == data_dir_for("paper-dry")
    assert "paper-dry" in str(cfg.journal_path)


def test_profile_loader_applies_before_dotenv(tmp_path, monkeypatch):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "paper-dry.env").write_text("AOA_UNIVERSE=TEST\n")
    (tmp_path / ".env").write_text("AOA_UNIVERSE=LOCAL\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AOA_UNIVERSE", raising=False)
    monkeypatch.setenv("AOA_PROFILE", "paper-dry")

    load_env_files()
    assert __import__("os").environ.get("AOA_UNIVERSE") == "TEST"


def test_profile_journal_paths_match_env():
    profiles_dir = Path(__file__).resolve().parents[1] / "profiles"
    for name in ("test", "paper-dry", "paper"):
        text = (profiles_dir / f"{name}.env").read_text()
        assert f"AOA_ENV={name}" in text
        assert f"AOA_JOURNAL_PATH=data/{name}/journal/aoa.jsonl" in text


def test_shell_env_overrides_profile(tmp_path, monkeypatch):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "paper-dry.env").write_text("AOA_UNIVERSE=FROM_PROFILE\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AOA_PROFILE", "paper-dry")
    monkeypatch.setenv("AOA_UNIVERSE", "FROM_SHELL")

    load_env_files()
    assert __import__("os").environ.get("AOA_UNIVERSE") == "FROM_SHELL"
