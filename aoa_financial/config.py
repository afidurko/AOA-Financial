"""Central configuration for AOA-Financial.

Everything that needs tuning lives here so the rest of the codebase reads
declaratively. Values can be overridden via environment variables (prefix
``AOA_``) or by constructing :class:`Config` directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Dict, List

# The brief: "analyze every stock ... since June 1960." This is the epoch the
# synthetic generator and all "max history" queries anchor to.
EPOCH_START = date(1960, 6, 1)

# Trading-day approximations used by annualisation math.
TRADING_DAYS_PER_YEAR = 252


def _env(name: str, default: str) -> str:
    return os.environ.get(f"AOA_{name}", default)


_DEFAULT_SWARM_WEIGHTS: Dict[str, float] = {
    "technical": 1.0,
    "fundamental": 1.1,
    "forecast": 1.0,
    "regime": 0.9,
    "sentiment": 0.6,
    "llm": 1.3,
}

_DEFAULT_FORECAST_WEIGHTS: Dict[str, float] = {
    "monte_carlo": 0.45,
    "trend": 0.35,
    "ewma": 0.20,
}


def _parse_weight_map(env_name: str, defaults: Dict[str, float]) -> Dict[str, float]:
    """Parse ``AOA_<env_name>`` as ``key:val,key:val`` (comma-separated)."""
    raw = os.environ.get(f"AOA_{env_name}")
    if not raw:
        return dict(defaults)
    out = dict(defaults)
    for part in raw.split(","):
        if ":" not in part:
            continue
        key, val = part.split(":", 1)
        key = key.strip()
        try:
            out[key] = float(val.strip())
        except ValueError:
            continue
    return out


@dataclass
class Config:
    """Runtime configuration.

    Attributes are intentionally plain so the object serialises cleanly to
    JSON for reproducibility (every analysis run can record the config used).
    """

    # --- storage ---------------------------------------------------------
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", ".aoa_data")))
    db_filename: str = field(default_factory=lambda: _env("DB_FILE", "market.db"))

    # --- data window -----------------------------------------------------
    epoch_start: date = EPOCH_START

    # --- LLM analyst -----------------------------------------------------
    # Default to the most capable Claude model per Anthropic guidance.
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "claude-opus-4-8"))
    llm_effort: str = field(default_factory=lambda: _env("LLM_EFFORT", "high"))
    llm_max_tokens: int = field(default_factory=lambda: int(_env("LLM_MAX_TOKENS", "8000")))

    # --- swarm weighting -------------------------------------------------
    # Relative trust placed in each specialist agent before confidence
    # weighting. Tuned so no single agent dominates.
    swarm_weights: Dict[str, float] = field(
        default_factory=lambda: _parse_weight_map("SWARM_WEIGHTS", _DEFAULT_SWARM_WEIGHTS)
    )
    forecast_weights: Dict[str, float] = field(
        default_factory=lambda: _parse_weight_map("FORECAST_WEIGHTS", _DEFAULT_FORECAST_WEIGHTS)
    )

    # A small but representative default universe spanning sectors. Any other
    # ticker can still be generated/loaded on demand.
    default_universe: List[str] = field(
        default_factory=lambda: [
            "AAPL", "MSFT", "AMZN", "GOOGL", "META",
            "JPM", "BAC", "XOM", "CVX", "JNJ",
            "PFE", "KO", "PG", "WMT", "GE",
            "F", "T", "IBM", "CAT", "BA",
        ]
    )

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["data_dir"] = str(self.data_dir)
        d["epoch_start"] = self.epoch_start.isoformat()
        d["db_path"] = str(self.db_path)
        return d
