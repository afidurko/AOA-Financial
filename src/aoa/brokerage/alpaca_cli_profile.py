"""Load Alpaca credentials from the official Alpaca CLI profile store.

Profiles live under ``~/.config/alpaca/profiles/`` (or ``ALPACA_CONFIG_DIR``).
Resolution order matches ``alpacahq/cli``:

1. ``ALPACA_API_KEY`` + ``ALPACA_SECRET_KEY`` env vars (CLI names)
2. Profile ``access_token`` (OAuth via ``alpaca profile login``)
3. Profile ``api_key`` + ``secret_key`` (``alpaca profile login --api-key``)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a project dependency
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class AlpacaCliProfile:
    profile_name: str
    key_id: str = ""
    secret_key: str = ""
    oauth_token: str = ""
    live_trade: bool = False

    @property
    def source(self) -> str:
        if self.oauth_token:
            return "cli-oauth"
        if self.key_id and self.secret_key:
            return "cli-api-key"
        return ""

    @property
    def is_valid(self) -> bool:
        return bool(self.oauth_token) or bool(self.key_id and self.secret_key)


def alpaca_config_dir() -> Path:
    override = os.environ.get("ALPACA_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "alpaca"


def resolve_profile_name(explicit: str = "") -> str:
    for candidate in (
        explicit.strip(),
        os.environ.get("AOA_ALPACA_PROFILE", "").strip(),
        os.environ.get("ALPACA_PROFILE", "").strip(),
    ):
        if candidate:
            return candidate
    cfg_path = alpaca_config_dir() / "config.yaml"
    if yaml is not None and cfg_path.is_file():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except OSError:
            data = {}
        default = str(data.get("default_profile", "")).strip()
        if default:
            return default
    return "paper"


def load_alpaca_cli_profile(profile_name: str = "") -> AlpacaCliProfile | None:
    """Return credentials from the Alpaca CLI profile store, or None if absent."""
    if yaml is None:
        return None

    name = resolve_profile_name(profile_name)
    path = alpaca_config_dir() / "profiles" / f"{name}.yaml"
    if not path.is_file():
        return None

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return None

    profile = AlpacaCliProfile(
        profile_name=name,
        key_id=str(raw.get("api_key", "") or "").strip(),
        secret_key=str(raw.get("secret_key", "") or "").strip(),
        oauth_token=str(raw.get("access_token", "") or "").strip(),
        live_trade=bool(raw.get("live_trade")),
    )
    return profile if profile.is_valid else None
