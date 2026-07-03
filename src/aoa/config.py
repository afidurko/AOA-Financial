"""Central configuration, loaded from environment variables.

A tiny ``.env`` loader is included so the project has no hard dependency on
``python-dotenv``; if that package is installed it is used, otherwise we parse
the file ourselves.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    """Populate ``os.environ`` from a ``.env`` file if present.

    Existing environment variables always win, so real secrets exported in the
    shell are never overwritten by the file.
    """
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class RiskLimits:
    """Hard guardrails. Orders violating any of these are rejected outright."""

    max_position_pct: float = 0.10
    max_options_pct: float = 0.15
    max_daily_loss_pct: float = 0.03
    min_cash_buffer_pct: float = 0.05
    max_orders_per_cycle: int = 5


@dataclass(frozen=True)
class Config:
    # LLM
    anthropic_api_key: str = ""
    model: str = "claude-opus-4-8"
    effort: str = "high"

    # Brokerage
    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_live: bool = False

    # Universe & cadence
    universe: tuple[str, ...] = ()
    cycle_seconds: int = 900

    # Execution
    dry_run: bool = False
    journal_path: str = "journal/aoa.jsonl"

    # News feed
    news_enabled: bool = True

    # Web server
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    web_auto_loop: bool = False

    # Risk
    risk: RiskLimits = field(default_factory=RiskLimits)

    @property
    def has_brokerage_creds(self) -> bool:
        return bool(self.alpaca_key_id and self.alpaca_secret_key)

    @property
    def trading_mode(self) -> str:
        if self.dry_run:
            return "dry-run"
        return "live" if self.alpaca_live else "paper"

    @classmethod
    def from_env(cls, load_dotenv: bool = True) -> Config:
        if load_dotenv:
            _load_dotenv()
        universe_raw = os.environ.get("AOA_UNIVERSE", "")
        universe = tuple(
            sym.strip().upper() for sym in universe_raw.split(",") if sym.strip()
        )
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("AOA_MODEL", "claude-opus-4-8"),
            effort=os.environ.get("AOA_EFFORT", "high"),
            alpaca_key_id=os.environ.get("ALPACA_API_KEY_ID", ""),
            alpaca_secret_key=os.environ.get("ALPACA_API_SECRET_KEY", ""),
            alpaca_live=_bool("ALPACA_LIVE", False),
            universe=universe,
            cycle_seconds=_int("AOA_CYCLE_SECONDS", 900),
            dry_run=_bool("AOA_DRY_RUN", False),
            journal_path=os.environ.get("AOA_JOURNAL_PATH", "journal/aoa.jsonl"),
            news_enabled=_bool("AOA_NEWS_ENABLED", True),
            web_host=os.environ.get("AOA_WEB_HOST", "0.0.0.0"),
            web_port=_int("AOA_WEB_PORT", 8080),
            web_auto_loop=_bool("AOA_WEB_AUTO_LOOP", False),
            risk=RiskLimits(
                max_position_pct=_float("AOA_MAX_POSITION_PCT", 0.10),
                max_options_pct=_float("AOA_MAX_OPTIONS_PCT", 0.15),
                max_daily_loss_pct=_float("AOA_MAX_DAILY_LOSS_PCT", 0.03),
                min_cash_buffer_pct=_float("AOA_MIN_CASH_BUFFER_PCT", 0.05),
                max_orders_per_cycle=_int("AOA_MAX_ORDERS_PER_CYCLE", 5),
            ),
        )

    def validate(self) -> list[str]:
        """Return a list of human-readable configuration problems (empty == OK)."""
        problems: list[str] = []
        if not self.anthropic_api_key:
            problems.append("ANTHROPIC_API_KEY is not set — the agents cannot reason.")
        if not self.has_brokerage_creds:
            problems.append(
                "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set — "
                "no market data or order execution is possible."
            )
        r = self.risk
        if not 0 < r.max_position_pct <= 1:
            problems.append("AOA_MAX_POSITION_PCT must be in (0, 1].")
        if not 0 <= r.min_cash_buffer_pct < 1:
            problems.append("AOA_MIN_CASH_BUFFER_PCT must be in [0, 1).")
        return problems
