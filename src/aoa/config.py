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
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


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
    """Hard guardrails. Orders violating any of these are rejected outright."""

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

    # Brokerage
    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_live: bool = False

    # Universe & cadence
    universe: tuple[str, ...] = ()
    cycle_seconds: int = 900

    # Execution
    dry_run: bool = False
    live_acknowledged: bool = False

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
            universe=universe,
            cycle_seconds=_int("AOA_CYCLE_SECONDS", 900),
            dry_run=_bool("AOA_DRY_RUN", False),
            live_acknowledged=live_ack,
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
        valid_effort = {"low", "medium", "high", "xhigh", "max"}
        if self.effort not in valid_effort:
            problems.append(
                f"AOA_EFFORT must be one of {sorted(valid_effort)} (got {self.effort!r})."
            )
        return problems
