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

from aoa.brokerage.constants import (
    VALID_ALPACA_BAR_ADJUSTMENTS,
    VALID_ALPACA_DATA_FEEDS,
)
from aoa.data.timeframes import DEFAULT_TIMEFRAMES, TimeframeSpec, parse_timeframes

VALID_BROKERS = frozenset({"moomoo", "alpaca"})
VALID_ENVS = frozenset({"test", "paper-dry", "paper", "live"})
_ENV_DEFAULTS: dict[str, dict[str, bool]] = {
    "test": {"dry_run": True, "alpaca_live": False},
    "paper-dry": {"dry_run": True, "alpaca_live": False},
    "paper": {"dry_run": False, "alpaca_live": False},
    "live": {"dry_run": False, "alpaca_live": True},
}


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


def _parse_csv_paths(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _resolve_alpaca_auth() -> tuple[str, str, str, str, str, bool | None]:
    """Return (key_id, secret, oauth_token, source, cli_profile, cli_live)."""
    key_id = os.environ.get("ALPACA_API_KEY_ID", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET_KEY", "").strip()
    if not key_id:
        key_id = os.environ.get("ALPACA_API_KEY", "").strip()
    if not secret:
        secret = os.environ.get("ALPACA_SECRET_KEY", "").strip()
    if key_id and secret:
        return key_id, secret, "", "env", "", None

    if not _bool("AOA_ALPACA_USE_CLI_PROFILE", True):
        return "", "", "", "", "", None

    from aoa.brokerage.alpaca_cli_profile import load_alpaca_cli_profile

    profile = load_alpaca_cli_profile()
    if profile is None:
        return "", "", "", "", "", None

    if profile.oauth_token:
        return "", "", profile.oauth_token, profile.source, profile.profile_name, profile.live_trade
    return (
        profile.key_id,
        profile.secret_key,
        "",
        profile.source,
        profile.profile_name,
        profile.live_trade,
    )


def data_dir_for(env: str) -> Path:
    base = Path(os.environ.get("AOA_DATA_DIR", "data"))
    return base / env


def journal_path_for(env: str) -> Path:
    override = os.environ.get("AOA_JOURNAL_PATH")
    if override:
        return Path(override)
    return data_dir_for(env) / "journal" / "aoa.jsonl"


def plasticity_path_for(env: str) -> Path:
    override = os.environ.get("AOA_PLASTICITY_PATH")
    if override:
        return Path(override)
    return data_dir_for(env) / "journal" / "plasticity.json"


def workloop_path_for(env: str) -> Path:
    override = os.environ.get("AOA_WORKLOOP_PATH")
    if override:
        return Path(override)
    return data_dir_for(env) / "workloop"


def analytics_db_path_for(env: str) -> Path:
    override = os.environ.get("AOA_ANALYTICS_DB_PATH")
    if override:
        return Path(override)
    return data_dir_for(env) / "analytics" / "aoa.sqlite"


def repair_path_for(env: str) -> Path:
    override = os.environ.get("AOA_REPAIR_PATH")
    if override:
        return Path(override)
    return data_dir_for(env) / "repair"


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
    plasticity_path: Path = field(default_factory=lambda: plasticity_path_for("paper-dry"))
    workloop_path: Path = field(default_factory=lambda: workloop_path_for("paper-dry"))
    analytics_db_path: Path = field(default_factory=lambda: analytics_db_path_for("paper-dry"))
    repair_path: Path = field(default_factory=lambda: repair_path_for("paper-dry"))

    # LLM
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-6"
    effort: str = "high"

    # Broker selection (default: Moomoo via OpenD)
    broker: str = "moomoo"
    moomoo_opend_host: str = "127.0.0.1"
    moomoo_opend_port: int = 11111
    moomoo_unlock_password: str = ""
    moomoo_acc_id: int = 0
    moomoo_acc_index: int = 0
    moomoo_security_firm: str = "FUTUINC"
    moomoo_market: str = "US"
    moomoo_live: bool = False

    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_oauth_token: str = ""
    alpaca_auth_source: str = ""
    alpaca_cli_profile: str = ""
    alpaca_live: bool = False
    alpaca_data_feed: str = ""
    alpaca_bar_adjustment: str = "split"

    universe: tuple[str, ...] = ()
    cycle_seconds: int = 900
    cycle_seconds_market_open: int = 0
    cycle_seconds_market_closed: int = 0

    # Analytics + notifications
    analytics_enabled: bool = True
    team_parallel: bool = True
    team_subagents_enabled: bool = True
    notify_push_opportunities: bool = True
    notify_push_halts: bool = True
    notify_min_conviction: float = 0.65

    # Idle opportunity sweep — market analysis when no alerts or opportunity pushes
    opportunity_sweep_enabled: bool = True
    opportunity_sweep_seconds: int = 900
    opportunity_sweep_poll_seconds: int = 60

    # Literature research (Semantic Scholar — user approval required)
    scholar_enabled: bool = True
    scholar_query: str = "algorithmic trading momentum portfolio optimization"
    scholar_max_results: int = 5

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
    openstock_url: str = ""

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

    # Journal-driven cross-cycle memory (neuroplasticity).
    plasticity_enabled: bool = True
    plasticity_tail: int = 200
    plasticity_max_lessons: int = 10

    # Autonomous work loop (discover → merge with Aaron approval gate)
    workloop_enabled: bool = True
    workloop_approver: str = "Aaron"
    workloop_user_approver: str = "user"
    workloop_team_review_enabled: bool = True
    workloop_escalation_file_threshold: int = 12
    workloop_journal_tail: int = 100
    workloop_max_lessons: int = 20
    workloop_auto_commit: bool = False
    workloop_allow_merge: bool = False
    workloop_base_branch: str = "main"
    workloop_extra_sources: tuple[str, ...] = ()
    workloop_interval_seconds: int = 3600

    # Fable 5 repair loop (loop-engineering L2: triage → minimal-fix → verifier)
    repair_enabled: bool = True
    repair_sync_state: bool = True
    repair_worktrees_dir: str = ".aoa-worktrees"

    trading_agents_enabled: bool = True
    trading_agents_debate_rounds: int = 1

    risk: RiskLimits = field(default_factory=RiskLimits)

    # Low-rank signal adaptation (LoRA-style online conviction recalibration)
    adapt_enabled: bool = False
    adapt_path: str = ".aoa/signal_adapter.json"
    adapt_rank: int = 4
    adapt_alpha: float = 8.0
    adapt_lr: float = 0.05
    adapt_return_scale: float = 0.05

    @property
    def has_brokerage_creds(self) -> bool:
        if self.broker == "moomoo":
            return True
        return bool(self.alpaca_oauth_token) or bool(
            self.alpaca_key_id and self.alpaca_secret_key
        )

    @property
    def is_live_broker(self) -> bool:
        return self.moomoo_live if self.broker == "moomoo" else self.alpaca_live

    @property
    def trading_mode(self) -> str:
        if self.dry_run:
            return "dry-run"
        return "live" if self.is_live_broker else "paper"

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
        alpaca_key_id, alpaca_secret, alpaca_oauth, alpaca_source, alpaca_cli_profile, cli_live = (
            _resolve_alpaca_auth()
        )
        alpaca_live = _bool("ALPACA_LIVE", False)
        if os.environ.get("ALPACA_LIVE_TRADE", "").strip():
            alpaca_live = _bool("ALPACA_LIVE_TRADE", False)
        elif cli_live is True and not os.environ.get("ALPACA_LIVE"):
            alpaca_live = True
        moomoo_live = (
            _bool("MOOMOO_LIVE", env == "live")
            if "MOOMOO_LIVE" not in os.environ
            else _bool("MOOMOO_LIVE", False)
        )

        return cls(
            env=env,
            profile=os.environ.get("AOA_PROFILE", "").strip(),
            data_dir=data_dir_for(env),
            journal_path=journal_path_for(env),
            plasticity_path=plasticity_path_for(env),
            workloop_path=workloop_path_for(env),
            analytics_db_path=analytics_db_path_for(env),
            repair_path=repair_path_for(env),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("AOA_MODEL", "claude-sonnet-4-6"),
            effort=os.environ.get("AOA_EFFORT", "high"),
            broker=os.environ.get("AOA_BROKER", "moomoo").strip().lower() or "moomoo",
            moomoo_opend_host=os.environ.get("MOOMOO_OPEND_HOST", "127.0.0.1").strip() or "127.0.0.1",
            moomoo_opend_port=_int("MOOMOO_OPEND_PORT", 11111),
            moomoo_unlock_password=os.environ.get("MOOMOO_UNLOCK_PASSWORD", ""),
            moomoo_acc_id=_int("MOOMOO_ACC_ID", 0),
            moomoo_acc_index=_int("MOOMOO_ACC_INDEX", 0),
            moomoo_security_firm=os.environ.get("MOOMOO_SECURITY_FIRM", "FUTUINC").strip() or "FUTUINC",
            moomoo_market=os.environ.get("MOOMOO_MARKET", "US").strip().upper() or "US",
            moomoo_live=moomoo_live,
            alpaca_key_id=alpaca_key_id,
            alpaca_secret_key=alpaca_secret,
            alpaca_oauth_token=alpaca_oauth,
            alpaca_auth_source=alpaca_source,
            alpaca_cli_profile=alpaca_cli_profile,
            alpaca_live=alpaca_live,
            alpaca_data_feed=os.environ.get("ALPACA_DATA_FEED", "").strip().lower(),
            alpaca_bar_adjustment=os.environ.get("ALPACA_BAR_ADJUSTMENT", "split").strip().lower(),
            universe=universe,
            cycle_seconds=_int("AOA_CYCLE_SECONDS", 900),
            cycle_seconds_market_open=_int("AOA_CYCLE_SECONDS_MARKET_OPEN", 0),
            cycle_seconds_market_closed=_int("AOA_CYCLE_SECONDS_MARKET_CLOSED", 0),
            analytics_enabled=_bool("AOA_ANALYTICS_ENABLED", True),
            team_parallel=_bool("AOA_TEAM_PARALLEL", True),
            team_subagents_enabled=_bool("AOA_TEAM_SUBAGENTS_ENABLED", True),
            notify_push_opportunities=_bool("AOA_NOTIFY_PUSH_OPPORTUNITIES", True),
            notify_push_halts=_bool("AOA_NOTIFY_PUSH_HALTS", True),
            notify_min_conviction=_float("AOA_NOTIFY_MIN_CONVICTION", 0.65),
            opportunity_sweep_enabled=_bool("AOA_OPPORTUNITY_SWEEP_ENABLED", True),
            opportunity_sweep_seconds=max(60, _int("AOA_OPPORTUNITY_SWEEP_SECONDS", 900)),
            opportunity_sweep_poll_seconds=max(15, _int("AOA_OPPORTUNITY_SWEEP_POLL_SECONDS", 60)),
            scholar_enabled=_bool("AOA_SCHOLAR_ENABLED", True),
            scholar_query=os.environ.get(
                "AOA_SCHOLAR_QUERY",
                "algorithmic trading momentum portfolio optimization",
            ).strip(),
            scholar_max_results=max(1, _int("AOA_SCHOLAR_MAX_RESULTS", 5)),
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
            openstock_url=os.environ.get("AOA_OPENSTOCK_URL", "").strip(),
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
            plasticity_enabled=_bool("AOA_PLASTICITY_ENABLED", True),
            plasticity_tail=max(20, _int("AOA_PLASTICITY_TAIL", 200)),
            plasticity_max_lessons=max(1, _int("AOA_PLASTICITY_MAX_LESSONS", 10)),
            adapt_enabled=_bool("AOA_ADAPT_ENABLED", False),
            adapt_path=os.environ.get("AOA_ADAPT_PATH", ".aoa/signal_adapter.json"),
            adapt_rank=_int("AOA_ADAPT_RANK", 4),
            adapt_alpha=_float("AOA_ADAPT_ALPHA", 8.0),
            adapt_lr=_float("AOA_ADAPT_LR", 0.05),
            adapt_return_scale=_float("AOA_ADAPT_RETURN_SCALE", 0.05),
            workloop_enabled=_bool("AOA_WORKLOOP_ENABLED", True),
            workloop_approver=os.environ.get("AOA_WORKLOOP_APPROVER", "Aaron").strip() or "Aaron",
            workloop_user_approver=os.environ.get("AOA_WORKLOOP_USER_APPROVER", "user").strip() or "user",
            workloop_team_review_enabled=_bool("AOA_WORKLOOP_TEAM_REVIEW_ENABLED", True),
            workloop_escalation_file_threshold=max(
                1, _int("AOA_WORKLOOP_ESCALATION_FILE_THRESHOLD", 12)
            ),
            workloop_journal_tail=max(20, _int("AOA_WORKLOOP_JOURNAL_TAIL", 100)),
            workloop_max_lessons=max(1, _int("AOA_WORKLOOP_MAX_LESSONS", 20)),
            workloop_auto_commit=_bool("AOA_WORKLOOP_AUTO_COMMIT", False),
            workloop_allow_merge=_bool("AOA_WORKLOOP_ALLOW_MERGE", False),
            workloop_base_branch=os.environ.get("AOA_WORKLOOP_BASE_BRANCH", "main").strip() or "main",
            workloop_extra_sources=_parse_csv_paths("AOA_WORKLOOP_EXTRA_SOURCES"),
            workloop_interval_seconds=max(60, _int("AOA_WORKLOOP_INTERVAL_SECONDS", 3600)),
            repair_enabled=_bool("AOA_REPAIR_ENABLED", True),
            repair_sync_state=_bool("AOA_REPAIR_SYNC_STATE", True),
            repair_worktrees_dir=os.environ.get("AOA_REPAIR_WORKTREES_DIR", ".aoa-worktrees").strip()
            or ".aoa-worktrees",
            trading_agents_enabled=_bool("AOA_TRADING_AGENTS_ENABLED", True),
            trading_agents_debate_rounds=max(1, _int("AOA_TRADING_AGENTS_DEBATE_ROUNDS", 1)),
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
        if self.broker not in VALID_BROKERS:
            problems.append(
                f"AOA_BROKER must be one of {sorted(VALID_BROKERS)} (got {self.broker!r})."
            )
        if self.env != "test":
            if not self.anthropic_api_key:
                problems.append("ANTHROPIC_API_KEY is not set — the agents cannot reason.")
            if self.broker == "alpaca" and not self.has_brokerage_creds:
                problems.append(
                    "Alpaca credentials missing — set ALPACA_API_KEY_ID and "
                    "ALPACA_API_SECRET_KEY in .env, or run "
                    "`alpaca profile login` (paper OAuth) / "
                    "`alpaca profile login --api-key`. See SETUP-AWAITING-YOU.md."
                )
            if self.broker == "moomoo" and self.env == "live" and not self.moomoo_unlock_password:
                problems.append(
                    "MOOMOO_UNLOCK_PASSWORD is required when AOA_ENV=live with Moomoo."
                )
        if self.broker == "alpaca" and self.alpaca_data_feed and self.alpaca_data_feed not in VALID_ALPACA_DATA_FEEDS:
            problems.append(
                "ALPACA_DATA_FEED must be one of: sip, iex, boats, otc (or leave blank)."
            )
        if self.broker == "alpaca" and self.alpaca_bar_adjustment not in VALID_ALPACA_BAR_ADJUSTMENTS:
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
