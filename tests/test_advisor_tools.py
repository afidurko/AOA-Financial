"""Tests for the advisor tool registry and profile (de)serialization."""

from __future__ import annotations

from aoa.advisor.profile import FinancialProfile, sample_profile
from aoa.advisor.tools import build_registry
from tests.conftest import FakeBroker


def test_profile_roundtrips_through_json(tmp_path):
    prof = sample_profile()
    path = tmp_path / "profile.json"
    prof.save(path)
    loaded = FinancialProfile.load(path)
    assert loaded.name == prof.name
    assert loaded.net_worth == prof.net_worth
    assert [d.name for d in loaded.debts] == [d.name for d in prof.debts]
    assert len(loaded.assets) == len(prof.assets)


def test_profile_derived_values():
    prof = sample_profile()
    assert prof.total_assets == sum(a.value for a in prof.assets)
    assert prof.net_worth == prof.total_assets - prof.total_liabilities
    # Only the taxable cash account counts as liquid.
    assert prof.liquid_savings == 18_000
    assert prof.years_to_retirement == 31


def test_registry_specs_are_well_formed():
    reg = build_registry(sample_profile())
    specs = reg.specs()
    assert {"get_financial_profile", "compute_net_worth", "debt_payoff"} <= set(reg.names())
    for spec in specs:
        assert set(spec) == {"name", "description", "input_schema"}
        assert spec["input_schema"]["type"] == "object"


def test_tool_run_net_worth_matches_profile():
    prof = sample_profile()
    reg = build_registry(prof)
    out = reg.run("compute_net_worth", {})
    assert out["net_worth"] == prof.net_worth


def test_tool_run_debt_payoff_uses_profile_debts():
    reg = build_registry(sample_profile())
    out = reg.run("debt_payoff", {"extra_monthly": 500, "strategy": "avalanche"})
    assert out["feasible"] is True
    assert out["months"] > 0
    # Highest-APR debt (credit card) should be cleared first under avalanche.
    assert out["payoff_order"][0] == "Credit card"


def test_tool_run_emergency_fund_override():
    reg = build_registry(sample_profile())
    out = reg.run("emergency_fund", {"target_months": 3})
    assert out["target_months"] == 3


def test_unknown_tool_returns_error():
    reg = build_registry(sample_profile())
    assert "error" in reg.run("does_not_exist", {})


def test_tool_errors_are_captured_not_raised():
    reg = build_registry(sample_profile())
    # contribution_room requires account_type; omitting it should not raise.
    out = reg.run("contribution_room", {})
    assert "error" in out


def test_portfolio_tool_registered_only_with_broker():
    assert "portfolio_snapshot" not in build_registry(sample_profile()).names()
    reg = build_registry(sample_profile(), broker=FakeBroker())
    assert "portfolio_snapshot" in reg.names()
    snap = reg.run("portfolio_snapshot", {})
    assert snap["broker"] == "fake"
    assert "positions" in snap
