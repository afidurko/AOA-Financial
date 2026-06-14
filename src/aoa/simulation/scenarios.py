"""A library of stress scenarios + extraction of scenarios from real history.

A :class:`Scenario` is simply a *path of daily simple returns* together with a
name, description, and tags. Applying that path to any starting price recreates
the shape of a historical episode — a crash, a melt-up, a choppy bear — so the
simulator can replay it against a current position.

Two ways to get a scenario:

* **Library** — stylized, deterministic recreations of well-known episodes
  (1987, 2008, the 2020 COVID crash, …). They are *not* the exact historical
  tape; they are reproducible return paths calibrated to the episode's headline
  drawdown, duration, and volatility, seeded so they never change between runs.
* **Extraction** — pull the real return path out of a window of live
  :class:`~aoa.brokerage.models.Bar` data with :func:`extract_scenario`.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from aoa.brokerage.models import Bar


@dataclass(frozen=True)
class Scenario:
    """A named path of daily simple returns."""

    name: str
    description: str
    daily_returns: tuple[float, ...]
    tags: tuple[str, ...] = ()

    @property
    def horizon_days(self) -> int:
        return len(self.daily_returns)

    @property
    def total_return_pct(self) -> float:
        growth = 1.0
        for r in self.daily_returns:
            growth *= 1 + r
        return round((growth - 1) * 100, 2)

    @property
    def max_drawdown_pct(self) -> float:
        """Worst peak-to-trough decline along the cumulative path."""
        level = 1.0
        peak = 1.0
        worst = 0.0
        for r in self.daily_returns:
            level *= 1 + r
            peak = max(peak, level)
            worst = min(worst, level / peak - 1)
        return round(worst * 100, 2)

    @property
    def worst_day_pct(self) -> float:
        return round(min(self.daily_returns) * 100, 2) if self.daily_returns else 0.0

    def apply(self, start_price: float) -> list[float]:
        """Project a price path from ``start_price`` along this scenario."""
        path = [start_price]
        for r in self.daily_returns:
            path.append(round(path[-1] * (1 + r), 6))
        return path

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "horizon_days": self.horizon_days,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "worst_day_pct": self.worst_day_pct,
            "tags": list(self.tags),
        }


def synthesize(
    name: str,
    description: str,
    *,
    days: int,
    drift: float,
    vol: float,
    shocks: dict[int, float] | None = None,
    tags: Sequence[str] = (),
    seed: int = 0,
) -> Scenario:
    """Build a reproducible scenario from a drift/vol process plus fixed shocks.

    ``drift`` and ``vol`` are per-day (simple-return space). ``shocks`` maps a
    day index to an *additive* return applied on top of that day's draw — this
    is how the headline crash days (e.g. −20% on Black Monday) are pinned in
    while the surrounding days wander realistically. The fixed ``seed`` makes the
    whole path deterministic, so a named scenario is identical on every run.
    """
    rng = random.Random(seed)
    shocks = shocks or {}
    returns: list[float] = []
    for i in range(days):
        r = drift + rng.gauss(0.0, vol)
        r += shocks.get(i, 0.0)
        returns.append(round(r, 6))
    return Scenario(name=name, description=description, daily_returns=tuple(returns), tags=tuple(tags))


# --------------------------------------------------------------- built-in library
def _library() -> dict[str, Scenario]:
    return {
        s.name: s
        for s in (
            synthesize(
                "black_monday_1987",
                "Single-session crash: a calm tape gives way to a ~22% one-day collapse.",
                days=20,
                drift=0.0005,
                vol=0.008,
                shocks={10: -0.22, 11: -0.05, 12: 0.06},
                tags=("crash", "tail-risk", "equity"),
                seed=1987,
            ),
            synthesize(
                "covid_crash_2020",
                "Fast ~34% bear over ~5 weeks on exogenous shock, then a sharp V-recovery.",
                days=60,
                drift=-0.002,
                vol=0.035,
                shocks={5: -0.06, 8: -0.075, 12: -0.12, 15: -0.05, 30: 0.09, 33: 0.06, 45: 0.05},
                tags=("crash", "v-recovery", "high-vol"),
                seed=2020,
            ),
            synthesize(
                "gfc_2008",
                "Grinding ~50% bear market with volatility clustering across a year.",
                days=252,
                drift=-0.0028,
                vol=0.026,
                shocks={120: -0.09, 122: -0.08, 130: 0.11, 180: -0.075, 200: -0.06},
                tags=("bear", "deleveraging", "high-vol"),
                seed=2008,
            ),
            synthesize(
                "dotcom_bust_2000",
                "Slow, persistent ~45% unwind of an overvalued growth complex.",
                days=252,
                drift=-0.0024,
                vol=0.018,
                tags=("bear", "valuation-reset"),
                seed=2000,
            ),
            synthesize(
                "flash_crash_2010",
                "Liquidity air-pocket: ~9% intraday plunge that largely round-trips.",
                days=10,
                drift=0.0006,
                vol=0.006,
                shocks={5: -0.09, 6: 0.075},
                tags=("crash", "liquidity", "mean-reverting"),
                seed=2010,
            ),
            synthesize(
                "rate_shock_2022",
                "Choppy bear: rate-driven repricing with vicious but failing rallies.",
                days=180,
                drift=-0.0012,
                vol=0.020,
                shocks={40: 0.06, 41: 0.05, 80: -0.055, 120: 0.07, 121: 0.04, 150: -0.06},
                tags=("bear", "choppy", "macro"),
                seed=2022,
            ),
            synthesize(
                "melt_up_2021",
                "Low-volatility grind higher: ~25% over the year with shallow dips.",
                days=252,
                drift=0.0011,
                vol=0.008,
                tags=("bull", "low-vol", "trend"),
                seed=2021,
            ),
            synthesize(
                "v_recovery",
                "Sharp ~25% drop followed by an equally sharp recovery to new highs.",
                days=40,
                drift=0.0,
                vol=0.015,
                shocks={5: -0.07, 8: -0.08, 10: -0.06, 20: 0.07, 24: 0.08, 28: 0.06},
                tags=("crash", "v-recovery"),
                seed=42,
            ),
            synthesize(
                "sideways_chop",
                "Directionless range-bound tape with moderate volatility.",
                days=120,
                drift=0.0,
                vol=0.012,
                tags=("sideways", "range-bound"),
                seed=7,
            ),
        )
    }


SCENARIO_LIBRARY: dict[str, Scenario] = _library()


def list_scenarios() -> list[Scenario]:
    """All built-in scenarios."""
    return list(SCENARIO_LIBRARY.values())


def get_scenario(name: str) -> Scenario:
    """Fetch a built-in scenario by name (raises ``KeyError`` if unknown)."""
    try:
        return SCENARIO_LIBRARY[name]
    except KeyError as exc:
        known = ", ".join(sorted(SCENARIO_LIBRARY)) or "(none)"
        raise KeyError(f"Unknown scenario {name!r}. Known scenarios: {known}.") from exc


def extract_scenario(
    bars: Sequence[Bar],
    name: str = "historical_window",
    description: str = "",
    *,
    start: int = 0,
    end: int | None = None,
) -> Scenario | None:
    """Turn a window of real bars into a replayable :class:`Scenario`.

    The window ``bars[start:end]`` is converted to its daily simple-return path.
    Returns ``None`` if the window has fewer than two bars.
    """
    window = bars[start:end]
    closes = [b.close for b in window]
    if len(closes) < 2:
        return None
    rets = tuple(
        round(closes[i] / closes[i - 1] - 1, 6)
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    )
    if not description:
        first = window[0].timestamp
        last = window[-1].timestamp
        description = f"Replay of {len(closes)} real bars ({first:%Y-%m-%d} → {last:%Y-%m-%d})."
    return Scenario(name=name, description=description, daily_returns=rets, tags=("historical",))
