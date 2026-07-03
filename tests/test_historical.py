"""Tests for the real historical return tapes."""

from __future__ import annotations

import pytest

from aoa.simulation import historical, scenarios


def test_all_tapes_present_and_nonempty():
    tapes = historical.historical_scenarios()
    names = {t.name for t in tapes}
    assert {
        "great_crash_1929_actual",
        "black_monday_1987_actual",
        "gfc_october_2008_actual",
        "covid_crash_2020_actual",
    } <= names
    for t in tapes:
        assert t.horizon_days > 0
        assert "actual" in t.tags and "historical" in t.tags


def test_black_monday_has_exact_record_day():
    sc = historical.get_historical("black_monday_1987_actual")
    # The −20.47% session is the worst single day in S&P 500 history.
    assert round(min(sc.daily_returns) * 100, 2) == -20.47
    assert sc.worst_day_pct == -20.47


def test_covid_tape_includes_worst_and_best_days():
    sc = historical.get_historical("covid_crash_2020_actual")
    rets_pct = [round(r * 100, 2) for r in sc.daily_returns]
    assert -11.98 in rets_pct  # Mar 16, 2020
    assert 9.38 in rets_pct  # Mar 24, 2020 rebound


def test_1929_is_dow_tagged():
    sc = historical.get_historical("great_crash_1929_actual")
    assert "dow" in sc.tags
    # Black Tuesday −11.73% is present.
    assert any(round(r * 100, 2) == -11.73 for r in sc.daily_returns)


def test_tapes_are_merged_into_main_library():
    lib = {s.name for s in scenarios.list_scenarios()}
    assert "covid_crash_2020_actual" in lib
    # Both the stylized and the real COVID scenarios coexist.
    assert "covid_crash_2020" in lib
    assert scenarios.get_scenario("gfc_october_2008_actual").horizon_days == 23


def test_merge_does_not_clobber_synthetic():
    # The synthetic black_monday_1987 must remain distinct from the real tape.
    synth = scenarios.get_scenario("black_monday_1987")
    real = scenarios.get_scenario("black_monday_1987_actual")
    assert synth.daily_returns != real.daily_returns


def test_get_unknown_historical_raises():
    with pytest.raises(KeyError):
        historical.get_historical("nope")


def test_apply_reproduces_real_drawdown():
    sc = historical.get_historical("covid_crash_2020_actual")
    path = sc.apply(100.0)
    assert path[0] == 100.0
    # The real COVID crash drew down roughly a third from the pre-crash peak.
    assert -40.0 < sc.max_drawdown_pct < -25.0
