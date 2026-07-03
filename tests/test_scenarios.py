"""Tests for the stress-scenario library and extraction."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aoa.brokerage.models import Bar
from aoa.simulation import scenarios


def _bars(closes):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=base + timedelta(days=i),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1_000,
        )
        for i, c in enumerate(closes)
    ]


def test_library_is_populated():
    lib = scenarios.list_scenarios()
    assert len(lib) >= 5
    names = {s.name for s in lib}
    assert "covid_crash_2020" in names
    assert "gfc_2008" in names


def test_scenarios_are_deterministic():
    # Rebuilding the library yields identical return paths (seeded synthesis).
    a = scenarios._library()["black_monday_1987"]
    b = scenarios._library()["black_monday_1987"]
    assert a.daily_returns == b.daily_returns


def test_black_monday_has_deep_one_day_shock():
    sc = scenarios.get_scenario("black_monday_1987")
    assert sc.worst_day_pct <= -20.0
    assert sc.max_drawdown_pct < -20.0


def test_apply_projects_price_path():
    sc = scenarios.Scenario("flat", "no move", (0.0, 0.0, 0.0))
    path = sc.apply(100.0)
    assert path == [100.0, 100.0, 100.0, 100.0]


def test_total_return_and_drawdown_math():
    sc = scenarios.Scenario("t", "", (0.10, -0.50))
    # 1.10 * 0.50 = 0.55 → -45%
    assert sc.total_return_pct == -45.0
    assert sc.max_drawdown_pct == -50.0


def test_get_unknown_scenario_raises():
    with pytest.raises(KeyError):
        scenarios.get_scenario("does_not_exist")


def test_extract_scenario_from_bars():
    sc = scenarios.extract_scenario(_bars([100, 110, 99]), "win")
    assert sc is not None
    assert sc.horizon_days == 2
    assert round(sc.daily_returns[0], 4) == 0.10


def test_extract_scenario_too_short():
    assert scenarios.extract_scenario(_bars([100]), "x") is None


def test_to_dict_keys():
    sc = scenarios.get_scenario("v_recovery")
    d = sc.to_dict()
    for key in ("name", "horizon_days", "total_return_pct", "max_drawdown_pct", "tags"):
        assert key in d
