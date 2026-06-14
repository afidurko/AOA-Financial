"""The advisor's tools — deterministic calculators exposed to Claude.

The agent reasons, but it must *call a tool* for every number it states. Each tool
is a thin wrapper that reads ground truth from the :class:`FinancialProfile`
(and, optionally, the live brokerage) and delegates the arithmetic to
:mod:`aoa.advisor.planning`. The model can also pass overrides to run "what-if"
scenarios (e.g. a different extra debt payment or expected return).

A :class:`ToolRegistry` bundles the JSON tool specs (for the Anthropic API) with
their Python implementations, and is fully exercisable without any LLM — which is
where most of the advisor's test coverage lives.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from aoa.advisor import planning
from aoa.advisor.profile import FinancialProfile
from aoa.brokerage.base import Broker, BrokerError

ToolFn = Callable[[dict], dict]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: ToolFn


class ToolRegistry:
    """Holds tools and runs them by name. Decoupled from the LLM on purpose."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[dict]:
        """Anthropic tool definitions."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]

    def run(self, name: str, payload: dict | None) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"unknown tool '{name}'"}
        try:
            return tool.fn(payload or {})
        except Exception as exc:  # noqa: BLE001 — surface tool errors to the model, don't crash
            return {"error": f"{type(exc).__name__}: {exc}"}


def _num(payload: dict, key: str, default: float) -> float:
    val = payload.get(key)
    return float(val) if val is not None else float(default)


_OBJ = {"type": "object", "additionalProperties": False}


def build_registry(profile: FinancialProfile, broker: Broker | None = None) -> ToolRegistry:
    """Wire the calculators to ``profile`` (and ``broker`` if available)."""
    reg = ToolRegistry()

    # --- profile snapshot --------------------------------------------------- #
    reg.register(Tool(
        "get_financial_profile",
        "Return the user's full financial profile (income, expenses, assets, "
        "debts, goals, assumptions). Call this first to ground every other tool.",
        {**_OBJ, "properties": {}},
        lambda p: profile.summary(),
    ))

    # --- cash flow ---------------------------------------------------------- #
    reg.register(Tool(
        "compute_net_worth",
        "Compute net worth = total assets - total liabilities, with a breakdown.",
        {**_OBJ, "properties": {}},
        lambda p: {
            "net_worth": planning.net_worth(profile.total_assets, profile.total_liabilities),
            "total_assets": profile.total_assets,
            "total_liabilities": profile.total_liabilities,
            "assets_by_category": profile.assets_by_category(),
        },
    ))

    reg.register(Tool(
        "savings_rate",
        "Compute monthly savings rate and surplus. Defaults to the profile's "
        "take-home income and expenses; pass overrides for what-if scenarios.",
        {**_OBJ, "properties": {
            "monthly_income": {"type": "number"},
            "monthly_expenses": {"type": "number"},
        }},
        lambda p: planning.savings_rate(
            _num(p, "monthly_income", profile.monthly_take_home),
            _num(p, "monthly_expenses", profile.monthly_expenses),
        ),
    ))

    reg.register(Tool(
        "emergency_fund",
        "Assess emergency-fund coverage: months of essential expenses covered by "
        "liquid savings, and any shortfall against the target.",
        {**_OBJ, "properties": {
            "target_months": {"type": "integer", "minimum": 0},
            "liquid_savings": {"type": "number"},
            "monthly_essential_expenses": {"type": "number"},
        }},
        lambda p: planning.emergency_fund(
            _num(p, "liquid_savings", profile.liquid_savings),
            _num(p, "monthly_essential_expenses", profile.monthly_essential_expenses),
            int(_num(p, "target_months", profile.emergency_fund_months_target)),
        ),
    ))

    # --- debt --------------------------------------------------------------- #
    reg.register(Tool(
        "debt_payoff",
        "Simulate paying off all debts with a given extra monthly payment, using "
        "the avalanche (highest APR first) or snowball (smallest balance first) "
        "strategy. Returns months to debt-free and total interest.",
        {**_OBJ, "properties": {
            "extra_monthly": {"type": "number", "minimum": 0},
            "strategy": {"type": "string", "enum": ["avalanche", "snowball"]},
        }},
        lambda p: planning.debt_payoff(
            [vars(d) for d in profile.debts],
            _num(p, "extra_monthly", 0.0),
            str(p.get("strategy", "avalanche")),
        ).to_dict(),
    ))

    reg.register(Tool(
        "compare_debt_strategies",
        "Compare avalanche vs snowball side by side for a given extra payment, "
        "including how much interest the avalanche method saves.",
        {**_OBJ, "properties": {"extra_monthly": {"type": "number", "minimum": 0}}},
        lambda p: planning.compare_debt_strategies(
            [vars(d) for d in profile.debts], _num(p, "extra_monthly", 0.0)
        ),
    ))

    # --- retirement --------------------------------------------------------- #
    reg.register(Tool(
        "retirement_projection",
        "Project the retirement nest egg in today's dollars and compare it to the "
        "amount needed to fund retirement spending at the safe-withdrawal rate. "
        "Defaults come from the profile; override any assumption for scenarios.",
        {**_OBJ, "properties": {
            "current_retirement_balance": {"type": "number"},
            "monthly_contribution": {"type": "number"},
            "years_to_retirement": {"type": "number"},
            "annual_return": {"type": "number"},
            "annual_retirement_expenses": {"type": "number"},
            "safe_withdrawal_rate": {"type": "number"},
        }},
        lambda p: planning.retirement_projection(
            _num(p, "current_retirement_balance", _retirement_balance(profile)),
            _num(p, "monthly_contribution", profile.monthly_retirement_contribution),
            _num(p, "years_to_retirement", profile.years_to_retirement),
            _num(p, "annual_return", profile.expected_return),
            annual_retirement_expenses=_num(
                p, "annual_retirement_expenses", profile.monthly_expenses * 12
            ),
            inflation=profile.inflation,
            safe_withdrawal_rate=_num(
                p, "safe_withdrawal_rate", profile.safe_withdrawal_rate
            ),
        ),
    ))

    reg.register(Tool(
        "future_value",
        "General compound-growth helper: future value of a starting balance plus "
        "fixed monthly contributions over N years at an annual return.",
        {**_OBJ, "properties": {
            "current_balance": {"type": "number"},
            "monthly_contribution": {"type": "number"},
            "years": {"type": "number"},
            "annual_return": {"type": "number"},
        }, "required": ["current_balance", "monthly_contribution", "years", "annual_return"]},
        lambda p: {"future_value": planning.future_value(
            _num(p, "current_balance", 0), _num(p, "monthly_contribution", 0),
            _num(p, "years", 0), _num(p, "annual_return", profile.expected_return),
        )},
    ))

    # --- allocation --------------------------------------------------------- #
    reg.register(Tool(
        "allocation_review",
        "Compare the current stock/bond/cash mix to an age- and risk-appropriate "
        "target equity allocation, and flag drift.",
        {**_OBJ, "properties": {
            "risk_tolerance": {"type": "string",
                               "enum": ["conservative", "moderate", "aggressive"]},
        }},
        lambda p: planning.allocation_review(
            profile.assets_by_category(),
            profile.age,
            str(p.get("risk_tolerance", profile.risk_tolerance)),
        ),
    ))

    # --- tax-advantaged room ----------------------------------------------- #
    reg.register(Tool(
        "contribution_room",
        "Remaining tax-advantaged contribution room for the year for a 401k, IRA, "
        "or HSA, including age-based catch-up contributions.",
        {**_OBJ, "properties": {
            "account_type": {"type": "string", "enum": ["401k", "ira", "hsa"]},
            "contributed_ytd": {"type": "number"},
            "year": {"type": "integer"},
        }, "required": ["account_type"]},
        lambda p: planning.contribution_room(
            str(p["account_type"]),
            profile.age,
            _num(p, "contributed_ytd", _ytd_for(profile, str(p["account_type"]))),
            year=int(_num(p, "year", planning.DEFAULT_TAX_YEAR)),
            hsa_coverage=profile.hsa_coverage,
        ),
    ))

    # --- live brokerage (optional) ----------------------------------------- #
    if broker is not None:
        reg.register(Tool(
            "portfolio_snapshot",
            "Read the user's LIVE brokerage account and open positions for an "
            "up-to-date view of investable assets and concentration.",
            {**_OBJ, "properties": {}},
            lambda p: _portfolio_snapshot(broker),
        ))

    return reg


def _retirement_balance(profile: FinancialProfile) -> float:
    """Sum assets held in retirement wrappers."""
    wrappers = {"401k", "ira", "roth_ira"}
    return round(sum(a.value for a in profile.assets if a.account_type in wrappers), 2)


def _ytd_for(profile: FinancialProfile, account_type: str) -> float:
    return {
        "401k": profile.ytd_401k_contribution,
        "ira": profile.ytd_ira_contribution,
        "hsa": profile.ytd_hsa_contribution,
    }.get(account_type.lower(), 0.0)


def _portfolio_snapshot(broker: Broker) -> dict:
    try:
        acct = broker.get_account()
        positions = broker.get_positions()
    except BrokerError as exc:
        return {"error": f"broker unavailable: {exc}"}
    total_mv = sum(p.market_value for p in positions) or 0.0
    return {
        "broker": broker.name,
        "equity": acct.equity,
        "cash": acct.cash,
        "positions": [
            {
                "symbol": p.symbol,
                "asset_class": p.asset_class.value,
                "market_value": round(p.market_value, 2),
                "unrealized_pl": round(p.unrealized_pl, 2),
                "weight": round(p.market_value / total_mv, 3) if total_mv else 0.0,
            }
            for p in positions
        ],
    }
