"""Central configuration, loaded from environment variables.

Configuration load order (lowest → highest priority):

1. Environment profile — ``profiles/{AOA_PROFILE or AOA_ENV}.env``
2. Local secrets file — ``.env``
3. Shell / process environment (always wins)

Set ``AOA_PROFILE=paper-dry`` or ``AOA_ENV=paper-dry`` to pick a profile. Named
environments also apply default ``AOA_DRY_RUN`` / ``ALPACA_LIVE`` values unless
those variables are already set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from aoa.data.timeframes import DEFAULT_TIMEFRAMES, TimeframeSpec, parse_timeframes

VALID_ENVS = frozenset({"test", "paper-dry", "paper", "live"})
_ENV_DEFAULTS: dict[str, dict[str, bool]] = {
    "test": {"dry_run": True, "alpaca_live": False},
    "paper-dry": {"dry_run": True, "alpaca_live": False},
    "paper": {"dry_run": False, "alpaca_live": False},
    "live": {"dry_run": False, "alpaca_live": True},
}
_VALID_DATA_FEEDS = frozenset({"", "sip", "iex", "boats", "otc"})
_VALID_BAR_ADJUSTMENTS = frozenset({"raw", "split", "dividend", "all", "spin-off"})


def _load_dotenv(path: str | os.PathLike[str]) -> None:
    """Populate ``os.environ`` from a dotenv file using ``setdefault``."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _profiles_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [Path.cwd() / "profiles", here.parents[2] / "profiles"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def _resolve_profile_path(name: str) -> Path | None:
    profile_dir = _profiles_dir()
    for candidate in (profile_dir / f"{name}.env", profile_dir / name):
        if candidate.is_file():
            return candidate
    return None


def load_env_files() -> None:
    """Load profile and local dotenv files into ``os.environ``."""
    profile_name = os.environ.get("AOA_PROFILE") or os.environ.get("AOA_ENV")
    if profile_name:
        profile_path = _resolve_profile_path(profile_name.strip())
        if profile_path is not None:
            _load_dotenv(profile_path)
    _load_dotenv(".env")


def _apply_env_defaults(env: str) -> None:
    defaults = _ENV_DEFAULTS.get(env, _ENV_DEFAULTS["paper-dry"])
    os.environ.setdefault(
        "AOA_DRY_RUN", "true" if defaults["dry_run"] else "false"
    )
    os.environ.setdefault(
        "ALPACA_LIVE", "true" if defaults["alpaca_live"] else "false"
    )


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


def data_dir_for(env: str) -> Path:
    base = Path(os.environ.get("AOA_DATA_DIR", "data"))
    return base / env


def journal_path_for(env: str) -> Path:
    override = os.environ.get("AOA_JOURNAL_PATH")
    if override:
        return Path(override)
    return data_dir_for(env) / "journal" / "aoa.jsonl"


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: float = 0.10
    max_options_pct: float = 0.15
    max_daily_loss_pct: float = 0.03
    min_cash_buffer_pct: float = 0.05
    max_orders_per_cycle: int = 5


@dataclass(frozen=True)
class Config:
    # Environment
    env: str = "paper-dry"
    profile: str = ""
    data_dir: Path = field(default_factory=lambda: data_dir_for("paper-dry"))
    journal_path: Path = field(default_factory=lambda: journal_path_for("paper-dry"))

    # LLM
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-20250514"
    effort: str = "high"

    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_live: bool = False
    alpaca_data_feed: str = ""
    alpaca_bar_adjustment: str = "split"

    universe: tuple[str, ...] = ()
    cycle_seconds: int = 900

    # News (Alpaca market-data feed)
    news_limit: int = 5
    news_lookback_hours: int = 72

    # Multi-timeframe historical bars (Alpaca bar API)
    bar_timeframes: tuple[TimeframeSpec, ...] = DEFAULT_TIMEFRAMES
    bar_feed: str = "iex"

    dry_run: bool = False
    live_acknowledged: bool = False
    parallel_workers: int = 4

    news_enabled: bool = True
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    web_auto_loop: bool = False

    # Aaron — iPhone push alerts (never email)
    custom_app_webhook_url: str = ""
    custom_app_api_key: str = ""
    custom_app_device_id: str = ""
    pushover_user_key: str = ""
    pushover_app_token: str = ""
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"

    # Persistent state (daily-loss baseline + settlement ledger).
    state_path: str = "journal/state.json"

    # Risk
    risk: RiskLimits = field(default_factory=RiskLimits)

    # Low-rank signal adaptation (LoRA-style online conviction recalibration)
    adapt_enabled: bool = False
    adapt_path: str = ".aoa/signal_adapter.json"
    adapt_rank: int = 4
    adapt_alpha: float = 8.0
    adapt_lr: float = 0.05

    @property
    def has_brokerage_creds(self) -> bool:
        return bool(self.alpaca_key_id and self.alpaca_secret_key)

    @property
    def trading_mode(self) -> str:
        if self.dry_run:
            return "dry-run"
        return "live" if self.alpaca_live else "paper"

    @property
    def is_test(self) -> bool:
        return self.env == "test"

    @classmethod
    def from_env(cls, load_dotenv: bool = True) -> Config:
        if load_dotenv:
            load_env_files()

        env = os.environ.get("AOA_ENV", "paper-dry").strip().lower()
        if env not in VALID_ENVS:
            env = "paper-dry"
        _apply_env_defaults(env)

        universe_raw = os.environ.get("AOA_UNIVERSE", "")
        universe = tuple(
            sym.strip().upper() for sym in universe_raw.split(",") if sym.strip()
        )
        live_ack = os.environ.get("AOA_LIVE_ACK", "").strip() == "I_UNDERSTAND"

        return cls(
            env=env,
            profile=os.environ.get("AOA_PROFILE", "").strip(),
            data_dir=data_dir_for(env),
            journal_path=journal_path_for(env),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("AOA_MODEL", "claude-sonnet-4-20250514"),
            effort=os.environ.get("AOA_EFFORT", "high"),
            alpaca_key_id=os.environ.get("ALPACA_API_KEY_ID", ""),
            alpaca_secret_key=os.environ.get("ALPACA_API_SECRET_KEY", ""),
            alpaca_live=_bool("ALPACA_LIVE", False),
            alpaca_data_feed=os.environ.get("ALPACA_DATA_FEED", "").strip().lower(),
            alpaca_bar_adjustment=os.environ.get("ALPACA_BAR_ADJUSTMENT", "split").strip().lower(),
            universe=universe,
            cycle_seconds=_int("AOA_CYCLE_SECONDS", 900),
            news_limit=_int("AOA_NEWS_LIMIT", 5),
            news_lookback_hours=_int("AOA_NEWS_LOOKBACK_HOURS", 72),
            bar_timeframes=parse_timeframes(os.environ.get("AOA_BAR_TIMEFRAMES", "")),
            bar_feed=os.environ.get("AOA_BAR_FEED", "iex").strip().lower() or "iex",
            dry_run=_bool("AOA_DRY_RUN", False),
            live_acknowledged=live_ack,
            parallel_workers=max(1, _int("AOA_PARALLEL_WORKERS", 4)),
            news_enabled=_bool("AOA_NEWS_ENABLED", True),
            web_host=os.environ.get("AOA_WEB_HOST", "0.0.0.0"),
            web_port=_int("AOA_WEB_PORT", 8080),
            web_auto_loop=_bool("AOA_WEB_AUTO_LOOP", False),
            custom_app_webhook_url=os.environ.get("AOA_CUSTOM_APP_WEBHOOK_URL", ""),
            custom_app_api_key=os.environ.get("AOA_CUSTOM_APP_API_KEY", ""),
            custom_app_device_id=os.environ.get("AOA_CUSTOM_APP_DEVICE_ID", ""),
            pushover_user_key=os.environ.get("AOA_PUSHOVER_USER_KEY", ""),
            pushover_app_token=os.environ.get("AOA_PUSHOVER_APP_TOKEN", ""),
            ntfy_topic=os.environ.get("AOA_NTFY_TOPIC", ""),
            ntfy_server=os.environ.get("AOA_NTFY_SERVER", "https://ntfy.sh"),
            state_path=os.environ.get(
                "AOA_STATE_PATH", str(data_dir_for(env) / "state.json")
            ),
            adapt_enabled=_bool("AOA_ADAPT_ENABLED", False),
            adapt_path=os.environ.get("AOA_ADAPT_PATH", ".aoa/signal_adapter.json"),
            adapt_rank=_int("AOA_ADAPT_RANK", 4),
            adapt_alpha=_float("AOA_ADAPT_ALPHA", 8.0),
            adapt_lr=_float("AOA_ADAPT_LR", 0.05),
            risk=RiskLimits(
                max_position_pct=_float("AOA_MAX_POSITION_PCT", 0.10),
                max_options_pct=_float("AOA_MAX_OPTIONS_PCT", 0.15),
                max_daily_loss_pct=_float("AOA_MAX_DAILY_LOSS_PCT", 0.03),
                min_cash_buffer_pct=_float("AOA_MIN_CASH_BUFFER_PCT", 0.05),
                max_orders_per_cycle=_int("AOA_MAX_ORDERS_PER_CYCLE", 5),
            ),
        )

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.env not in VALID_ENVS:
            problems.append(
                f"AOA_ENV must be one of {sorted(VALID_ENVS)} (got {self.env!r})."
            )
        if self.env == "live" and not self.live_acknowledged:
            problems.append(
                "AOA_LIVE_ACK=I_UNDERSTAND is required when AOA_ENV=live."
            )
        if self.env != "test":
            if not self.anthropic_api_key:
                problems.append("ANTHROPIC_API_KEY is not set — the agents cannot reason.")
            if not self.has_brokerage_creds:
                problems.append(
                    "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set — "
                    "no market data or order execution is possible."
                )
        if self.alpaca_data_feed and self.alpaca_data_feed not in _VALID_DATA_FEEDS - {""}:
            problems.append(
                "ALPACA_DATA_FEED must be one of: sip, iex, boats, otc (or leave blank)."
            )
        if self.alpaca_bar_adjustment not in _VALID_BAR_ADJUSTMENTS:
            problems.append(
                "ALPACA_BAR_ADJUSTMENT must be one of: raw, split, dividend, all, spin-off."
            )
        r = self.risk
        if not 0 < r.max_position_pct <= 1:
            problems.append("AOA_MAX_POSITION_PCT must be in (0, 1].")
        if not 0 <= r.min_cash_buffer_pct < 1:
            problems.append("AOA_MIN_CASH_BUFFER_PCT must be in [0, 1).")
        if not 0 < r.max_options_pct <= 1:
            problems.append("AOA_MAX_OPTIONS_PCT must be in (0, 1].")
        if not 0 < r.max_daily_loss_pct <= 1:
            problems.append("AOA_MAX_DAILY_LOSS_PCT must be in (0, 1].")
        if r.max_orders_per_cycle < 1:
            problems.append("AOA_MAX_ORDERS_PER_CYCLE must be >= 1.")
        if self.bar_feed not in {"iex", "sip", "otc", "boats"}:
            problems.append("AOA_BAR_FEED must be one of: iex, sip, otc, boats.")
        valid_effort = {"low", "medium", "high", "xhigh", "max"}
        if self.effort not in valid_effort:
            problems.append(
                f"AOA_EFFORT must be one of {sorted(valid_effort)} (got {self.effort!r})."
            )
        return problems
