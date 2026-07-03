"""Real historical return tapes — the *actual* shape of famous episodes.

Unlike the seeded, stylized scenarios in :mod:`aoa.simulation.scenarios` (which
are randomly generated to a target drawdown/vol), every scenario here is the
**real sequence of daily percentage returns** of a major index across a famous
window, taken from public daily closes. They reproduce history's exact path —
the actual gap-downs, the record up-days, the order in which they happened.

.. warning::

   These are approximate reconstructions of public index daily returns, rounded
   to two decimals from published closes, and are provided for research and
   illustration. Headline days (e.g. −20.47% on 1987-10-19) are well documented;
   surrounding days may differ slightly from a given data vendor. Verify against
   an authoritative source before relying on exact figures. The 1929 tape is the
   Dow Jones Industrial Average; the others are the S&P 500.
"""

from __future__ import annotations

from collections.abc import Sequence

from aoa.simulation.scenarios import Scenario


def _tape(
    name: str, description: str, pct_returns: Sequence[float], tags: Sequence[str]
) -> Scenario:
    """Build a Scenario from a list of daily returns expressed in **percent**."""
    return Scenario(
        name=name,
        description=description,
        daily_returns=tuple(round(p / 100.0, 6) for p in pct_returns),
        tags=tuple(tags),
    )


# 1929-10-23 → 1929-10-31, Dow Jones Industrial Average. Black Thursday (24th),
# Black Monday (28th, −12.82%), Black Tuesday (29th, −11.73%).
GREAT_CRASH_1929_ACTUAL = _tape(
    "great_crash_1929_actual",
    "Actual DJIA daily returns through the Oct 1929 crash (Black Monday/Tuesday).",
    [-6.33, -2.09, 0.58, -12.82, -11.73, 12.34, 5.82],
    ("crash", "historical", "actual", "dow"),
)

# 1987-10-14 → 1987-10-26, S&P 500. Black Monday (19th) is the worst single day
# in S&P history at −20.47%.
BLACK_MONDAY_1987_ACTUAL = _tape(
    "black_monday_1987_actual",
    "Actual S&P 500 daily returns around Black Monday 1987 (−20.47% on the 19th).",
    [-2.95, -2.34, -5.16, -20.47, 5.33, 9.10, -3.92, 0.16, -8.28],
    ("crash", "historical", "actual", "tail-risk"),
)

# 2008-10-01 → 2008-10-31, S&P 500. The peak-panic month of the GFC: −9.03% on
# the 15th, then a record +11.58% on the 13th and +10.79% on the 28th.
GFC_OCTOBER_2008_ACTUAL = _tape(
    "gfc_october_2008_actual",
    "Actual S&P 500 daily returns for October 2008 (GFC peak panic).",
    [
        -0.45, -4.03, -1.35, -3.85, -5.74, -1.13, -7.62, -1.18, 11.58, -0.53,
        -9.03, 4.25, -0.62, 4.77, -3.08, -6.10, 1.26, -3.45, -3.18, 10.79,
        -1.11, 2.58, 1.54,
    ],
    ("bear", "historical", "actual", "high-vol"),
)

# 2020-02-24 → 2020-03-24, S&P 500. The fastest bear market on record: −9.51%
# (Mar 12), −11.98% (Mar 16, worst since 1987), with +9.29% / +9.38% rebounds.
COVID_CRASH_2020_ACTUAL = _tape(
    "covid_crash_2020_actual",
    "Actual S&P 500 daily returns for the Feb–Mar 2020 COVID crash & rebound.",
    [
        -3.35, -3.03, -0.38, -4.42, -0.82, 4.60, -2.81, 4.22, -3.39, -1.71,
        -7.60, 4.94, -4.89, -9.51, 9.29, -11.98, 6.00, -5.18, 0.47, -4.34,
        -2.93, 9.38,
    ],
    ("crash", "historical", "actual", "v-recovery", "high-vol"),
)


HISTORICAL_TAPES: dict[str, Scenario] = {
    s.name: s
    for s in (
        GREAT_CRASH_1929_ACTUAL,
        BLACK_MONDAY_1987_ACTUAL,
        GFC_OCTOBER_2008_ACTUAL,
        COVID_CRASH_2020_ACTUAL,
    )
}


def historical_scenarios() -> list[Scenario]:
    """All real historical return tapes."""
    return list(HISTORICAL_TAPES.values())


def get_historical(name: str) -> Scenario:
    """Fetch a historical tape by name (raises ``KeyError`` if unknown)."""
    try:
        return HISTORICAL_TAPES[name]
    except KeyError as exc:
        known = ", ".join(sorted(HISTORICAL_TAPES)) or "(none)"
        raise KeyError(f"Unknown historical tape {name!r}. Known: {known}.") from exc
