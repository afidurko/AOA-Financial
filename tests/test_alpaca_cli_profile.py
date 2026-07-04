"""Tests for Alpaca CLI profile credential loading."""

from __future__ import annotations

from aoa.brokerage.alpaca_cli_profile import (
    load_alpaca_cli_profile,
    resolve_profile_name,
)


def test_resolve_profile_name_prefers_explicit():
    assert resolve_profile_name("prod") == "prod"


def test_load_oauth_profile(tmp_path, monkeypatch):
    config_dir = tmp_path / "alpaca"
    profiles = config_dir / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "paper.yaml").write_text(
        'access_token: "oauth-token-123"\nscopes: "trading data"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ALPACA_CONFIG_DIR", str(config_dir))

    profile = load_alpaca_cli_profile("paper")
    assert profile is not None
    assert profile.oauth_token == "oauth-token-123"
    assert profile.source == "cli-oauth"
    assert profile.key_id == ""


def test_load_api_key_profile(tmp_path, monkeypatch):
    config_dir = tmp_path / "alpaca"
    profiles = config_dir / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "paper.yaml").write_text(
        'api_key: "PKTEST123"\nsecret_key: "secret456"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("ALPACA_CONFIG_DIR", str(config_dir))

    profile = load_alpaca_cli_profile("paper")
    assert profile is not None
    assert profile.key_id == "PKTEST123"
    assert profile.secret_key == "secret456"
    assert profile.source == "cli-api-key"


def test_missing_profile_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_CONFIG_DIR", str(tmp_path))
    assert load_alpaca_cli_profile("paper") is None
