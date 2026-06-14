"""Unit tests for the deterministic personal-finance math."""

from __future__ import annotations

import math

from aoa.advisor import planning


def test_net_worth():
    assert planning.net_worth(150_000, 40_000) == 110_000


def test_savings_rate():
    r = planning.savings_rate(8_000, 6_000)
    assert r["savings_rate"] == 0.25
    assert r["monthly_surplus"] == 2_000
    assert r["annual_surplus"] == 24_000


def test_savings_rate_guards_zero_income():
    assert planning.savings_rate(0, 1_000)["savings_rate"] == 0.0


def test_emergency_fund_shortfall():
    r = planning.emergency_fund(12_000, 4_000, target_months=6)
    assert r["months_covered"] == 3.0
    assert r["target_dollars"] == 24_000
    assert r["shortfall"] == 12_000
    assert r["is_funded"] is False


def test_emergency_fund_funded():
    r = planning.emergency_fund(30_000, 4_000, target_months=6)
    assert r["is_funded"] is True
    assert r["shortfall"] == 0.0


def test_debt_payoff_zero_interest_is_exact():
    debts = [{"name": "card", "balance": 1_000, "apr": 0.0, "min_payment": 100}]
    plan = planning.debt_payoff(debts, extra_monthly=0, strategy="avalanche")
    assert plan.feasible is True
    assert plan.months == 10
    assert plan.total_interest == 0.0
    assert plan.payoff_order == ["card"]


def test_debt_payoff_extra_payment_speeds_things_up():
    debts = [{"name": "card", "balance": 1_000, "apr": 0.20, "min_payment": 50}]
    slow = planning.debt_payoff(debts, extra_monthly=0)
    fast = planning.debt_payoff(debts, extra_monthly=200)
    assert fast.months < slow.months
    assert fast.total_interest < slow.total_interest


def test_avalanche_beats_snowball_on_interest():
    debts = [
        {"name": "high_apr_small", "balance": 2_000, "apr": 0.24, "min_payment": 50},
        {"name": "low_apr_big", "balance": 10_000, "apr": 0.05, "min_payment": 150},
    ]
    cmp = planning.compare_debt_strategies(debts, extra_monthly=300)
    assert cmp["interest_saved_by_avalanche"] >= 0
    assert cmp["avalanche"]["total_interest"] <= cmp["snowball"]["total_interest"]


def test_debt_payoff_detects_infeasible_budget():
    # Interest (~$25/mo) exceeds the $20 payment, so the balance can never fall.
    debts = [{"name": "card", "balance": 1_000, "apr": 0.30, "min_payment": 20}]
    plan = planning.debt_payoff(debts, extra_monthly=0)
    assert plan.feasible is False
    assert "do not cover interest" in plan.note


def test_future_value_zero_return():
    assert planning.future_value(1_000, 100, 1, 0.0) == 2_200


def test_future_value_with_growth():
    fv = planning.future_value(0, 100, 1, 0.12)
    assert math.isclose(fv, 1268.25, rel_tol=1e-3)


def test_required_contribution_zero_when_on_track():
    # A huge starting balance already exceeds the target.
    assert planning.required_contribution(1_000_000, 100_000, 10, 0.05) == 0.0


def test_retirement_projection_keys_and_direction():
    r = planning.retirement_projection(
        200_000, 1_500, 30, 0.07,
        annual_retirement_expenses=60_000, inflation=0.03, safe_withdrawal_rate=0.04,
    )
    assert r["target_nest_egg"] == 1_500_000  # 60k / 0.04
    assert isinstance(r["on_track"], bool)
    assert "projected_nest_egg_today_dollars" in r


def test_target_equity_pct_glidepath():
    assert planning.target_equity_pct(34, "moderate") == 76
    assert planning.target_equity_pct(34, "aggressive") == 86
    assert planning.target_equity_pct(34, "conservative") == 66
    # clamps
    assert planning.target_equity_pct(5, "aggressive") == 95
    assert planning.target_equity_pct(120, "conservative") == 10


def test_allocation_review_flags_overweight():
    r = planning.allocation_review(
        {"equity": 90_000, "bond": 10_000, "cash": 0.0}, age=60, risk_tolerance="moderate"
    )
    assert r["current_equity_pct"] == 0.9
    assert r["drift"] > 0
    assert "overweight" in r["action"]


def test_contribution_room_catch_up_bands():
    # Under 50: base only.
    assert planning.contribution_room("401k", 40, 10_000, year=2025)["remaining_room"] == 13_500
    # 50–59: standard catch-up.
    assert planning.contribution_room("401k", 55, 0, year=2025)["annual_limit"] == 31_000
    # 60–63: SECURE 2.0 enhanced catch-up.
    assert planning.contribution_room("401k", 61, 0, year=2025)["annual_limit"] == 34_750
    # IRA catch-up at 50+.
    assert planning.contribution_room("ira", 50, 0, year=2025)["annual_limit"] == 8_000
    # HSA self with 55+ catch-up.
    assert planning.contribution_room("hsa", 56, 0, year=2025)["annual_limit"] == 5_300


def test_contribution_room_unknown_account():
    assert "note" in planning.contribution_room("brokerage", 40, 0)
