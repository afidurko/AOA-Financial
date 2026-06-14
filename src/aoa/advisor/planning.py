"""Deterministic personal-finance math.

These are pure functions of their inputs — no LLM, no network, no I/O — exactly
like :mod:`aoa.risk.guards`. The advisor agent is forbidden from doing arithmetic
in its head; it must call one of these (via :mod:`aoa.advisor.tools`) for every
number it states. That makes the numbers correct, testable, and auditable.

All figures are nominal USD unless a function documents otherwise. Tax-advantaged
contribution limits are *data*, kept in ``CONTRIBUTION_LIMITS`` and clearly dated;
verify them against current IRS publications before relying on them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# --------------------------------------------------------------------------- #
#  Tax-advantaged contribution limits (VERIFY against IRS before relying on).   #
#  Sources: IRS Notice annual cost-of-living adjustments. 2025 figures are      #
#  well-established; 2026 figures reflect the announced COLA and should be       #
#  re-checked. Override by passing ``limits=`` / ``year=`` where supported.      #
# --------------------------------------------------------------------------- #
CONTRIBUTION_LIMITS: dict[int, dict] = {
    2025: {
        "401k": 23_500,
        "401k_catchup_50": 7_500,
        "401k_catchup_60_63": 11_250,  # SECURE 2.0 enhanced catch-up
        "ira": 7_000,
        "ira_catchup_50": 1_000,
        "hsa_self": 4_300,
        "hsa_family": 8_550,
        "hsa_catchup_55": 1_000,
    },
    2026: {
        "401k": 24_500,
        "401k_catchup_50": 8_000,
        "401k_catchup_60_63": 11_250,
        "ira": 7_500,
        "ira_catchup_50": 1_100,
        "hsa_self": 4_400,
        "hsa_family": 8_750,
        "hsa_catchup_55": 1_000,
    },
}
DEFAULT_TAX_YEAR = 2026


# ------------------------------------------------------------------ cash flow
def net_worth(total_assets: float, total_liabilities: float) -> float:
    return round(total_assets - total_liabilities, 2)


def savings_rate(monthly_income: float, monthly_expenses: float) -> dict:
    """Share of take-home income not spent. Returns rate plus the dollar surplus."""
    if monthly_income <= 0:
        return {"savings_rate": 0.0, "monthly_surplus": 0.0, "note": "income must be > 0"}
    surplus = monthly_income - monthly_expenses
    return {
        "savings_rate": round(surplus / monthly_income, 4),
        "monthly_surplus": round(surplus, 2),
        "annual_surplus": round(surplus * 12, 2),
    }


def emergency_fund(
    liquid_savings: float, monthly_essential_expenses: float, target_months: int = 6
) -> dict:
    """Months of essential spending covered by liquid savings, and any shortfall."""
    if monthly_essential_expenses <= 0:
        return {"months_covered": 0.0, "note": "essential expenses must be > 0"}
    months = liquid_savings / monthly_essential_expenses
    target_dollars = target_months * monthly_essential_expenses
    return {
        "months_covered": round(months, 1),
        "target_months": target_months,
        "target_dollars": round(target_dollars, 2),
        "shortfall": round(max(0.0, target_dollars - liquid_savings), 2),
        "is_funded": months >= target_months,
    }


# ----------------------------------------------------------------------- debt
@dataclass
class PayoffPlan:
    strategy: str
    months: int
    total_interest: float
    payoff_order: list[str]
    feasible: bool
    monthly_outlay: float
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def debt_payoff(
    debts: list[dict],
    extra_monthly: float = 0.0,
    strategy: str = "avalanche",
    *,
    max_months: int = 1200,
) -> PayoffPlan:
    """Simulate paying off ``debts`` month by month.

    ``debts`` is a list of ``{"name", "balance", "apr", "min_payment"}``. The total
    monthly outlay is held constant (sum of minimums + ``extra_monthly``); as each
    debt clears, its freed minimum rolls into the target debt — the standard
    "debt snowball/avalanche rollover".

    - ``avalanche``: attack the highest APR first (minimizes interest).
    - ``snowball`` : attack the smallest balance first (fastest wins).
    """
    active = [
        {"name": d["name"], "balance": float(d["balance"]),
         "apr": float(d["apr"]), "min_payment": float(d["min_payment"])}
        for d in debts if float(d.get("balance", 0)) > 0
    ]
    if not active:
        return PayoffPlan(strategy, 0, 0.0, [], True, 0.0, "no outstanding debt")

    fixed_budget = sum(d["min_payment"] for d in active) + max(0.0, extra_monthly)
    total_interest = 0.0
    payoff_order: list[str] = []
    months = 0

    def _priority(items: list[dict]) -> list[dict]:
        if strategy == "snowball":
            return sorted(items, key=lambda d: d["balance"])
        return sorted(items, key=lambda d: d["apr"], reverse=True)  # avalanche

    while any(d["balance"] > 0.005 for d in active) and months < max_months:
        months += 1
        outstanding_before = sum(d["balance"] for d in active)

        # Accrue one month of interest.
        for d in active:
            if d["balance"] > 0:
                interest = d["balance"] * d["apr"] / 12
                d["balance"] += interest
                total_interest += interest

        pool = fixed_budget
        # 1) Pay minimums on every still-open debt.
        for d in active:
            if d["balance"] <= 0 or pool <= 0:
                continue
            pay = min(d["min_payment"], d["balance"], pool)
            d["balance"] -= pay
            pool -= pay
        # 2) Funnel everything left to the priority debt(s).
        for d in _priority([d for d in active if d["balance"] > 0.005]):
            if pool <= 0:
                break
            pay = min(d["balance"], pool)
            d["balance"] -= pay
            pool -= pay

        for d in active:
            if 0 < d["balance"] <= 0.005:
                d["balance"] = 0.0
            if d["balance"] == 0.0 and d["name"] not in payoff_order:
                payoff_order.append(d["name"])

        # Feasibility: if the budget can't even dent the principal, bail out.
        outstanding_after = sum(d["balance"] for d in active)
        if outstanding_after >= outstanding_before - 0.005:
            return PayoffPlan(
                strategy, months, round(total_interest, 2), payoff_order, False,
                round(fixed_budget, 2),
                "minimum payments do not cover interest — balance will not fall; "
                "increase the monthly payment",
            )

    feasible = all(d["balance"] <= 0.005 for d in active)
    return PayoffPlan(
        strategy,
        months,
        round(total_interest, 2),
        payoff_order,
        feasible,
        round(fixed_budget, 2),
        "" if feasible else f"not paid off within {max_months} months",
    )


def compare_debt_strategies(debts: list[dict], extra_monthly: float = 0.0) -> dict:
    """Run both strategies so the advisor can show the interest/speed tradeoff."""
    av = debt_payoff(debts, extra_monthly, "avalanche")
    sn = debt_payoff(debts, extra_monthly, "snowball")
    return {
        "avalanche": av.to_dict(),
        "snowball": sn.to_dict(),
        "interest_saved_by_avalanche": round(sn.total_interest - av.total_interest, 2),
    }


# ------------------------------------------------------------------ retirement
def future_value(
    current_balance: float,
    monthly_contribution: float,
    years: float,
    annual_return: float,
) -> float:
    """FV of a lump sum plus an ordinary (end-of-month) monthly annuity."""
    n = int(round(years * 12))
    r = annual_return / 12
    if n <= 0:
        return round(current_balance, 2)
    if abs(r) < 1e-12:
        return round(current_balance + monthly_contribution * n, 2)
    growth = (1 + r) ** n
    fv_principal = current_balance * growth
    fv_contrib = monthly_contribution * (growth - 1) / r
    return round(fv_principal + fv_contrib, 2)


def required_contribution(
    current_balance: float,
    target: float,
    years: float,
    annual_return: float,
) -> float:
    """Monthly contribution needed to reach ``target`` (0 if already on track)."""
    n = int(round(years * 12))
    r = annual_return / 12
    if n <= 0:
        return 0.0
    growth = (1 + r) ** n
    needed = target - current_balance * growth
    if needed <= 0:
        return 0.0
    if abs(r) < 1e-12:
        return round(needed / n, 2)
    return round(needed * r / (growth - 1), 2)


def retirement_projection(
    current_retirement_balance: float,
    monthly_contribution: float,
    years_to_retirement: float,
    annual_return: float,
    *,
    annual_retirement_expenses: float,
    inflation: float = 0.03,
    safe_withdrawal_rate: float = 0.04,
) -> dict:
    """Project the nest egg and compare it to the income it must replace.

    Works in **today's dollars** by using a real (inflation-adjusted) return, so
    the target and the projection are directly comparable without forecasting
    future price levels.
    """
    real_return = (1 + annual_return) / (1 + inflation) - 1
    projected = future_value(
        current_retirement_balance, monthly_contribution, years_to_retirement, real_return
    )
    target = annual_retirement_expenses / safe_withdrawal_rate if safe_withdrawal_rate else 0.0
    gap = target - projected
    needed_monthly = required_contribution(
        current_retirement_balance, target, years_to_retirement, real_return
    )
    return {
        "projected_nest_egg_today_dollars": round(projected, 2),
        "target_nest_egg": round(target, 2),
        "real_return_assumed": round(real_return, 4),
        "on_track": gap <= 0,
        "surplus_or_gap": round(-gap, 2),  # positive = surplus, negative = shortfall
        "sustainable_annual_income": round(projected * safe_withdrawal_rate, 2),
        "required_monthly_contribution": round(needed_monthly, 2),
        "additional_monthly_needed": round(max(0.0, needed_monthly - monthly_contribution), 2),
    }


# -------------------------------------------------------------- asset allocation
def target_equity_pct(age: int, risk_tolerance: str = "moderate") -> int:
    """Age-based glide path for the stock allocation, tilted by risk tolerance."""
    anchor = {"conservative": 100, "moderate": 110, "aggressive": 120}.get(
        risk_tolerance, 110
    )
    return max(10, min(95, anchor - age))


def allocation_review(
    assets_by_category: dict[str, float],
    age: int,
    risk_tolerance: str = "moderate",
    *,
    drift_tolerance: float = 0.05,
) -> dict:
    """Compare the current stock/bond mix to an age-appropriate target."""
    total = sum(assets_by_category.values())
    if total <= 0:
        return {"note": "no assets to allocate"}
    equity = assets_by_category.get("equity", 0.0) + assets_by_category.get("crypto", 0.0)
    bond = assets_by_category.get("bond", 0.0)
    cash = assets_by_category.get("cash", 0.0)
    other = total - equity - bond - cash

    current_equity_pct = equity / total
    target = target_equity_pct(age, risk_tolerance) / 100
    drift = current_equity_pct - target
    if drift > drift_tolerance:
        action = "overweight equities — consider trimming stocks toward bonds/cash"
    elif drift < -drift_tolerance:
        action = "underweight equities — consider adding to stocks"
    else:
        action = "allocation is within tolerance of target"
    return {
        "current_equity_pct": round(current_equity_pct, 3),
        "target_equity_pct": round(target, 3),
        "drift": round(drift, 3),
        "within_tolerance": abs(drift) <= drift_tolerance,
        "action": action,
        "breakdown": {
            "equity": round(equity, 2),
            "bond": round(bond, 2),
            "cash": round(cash, 2),
            "other": round(other, 2),
        },
    }


# ------------------------------------------------------ tax-advantaged accounts
def contribution_room(
    account_type: str,
    age: int,
    contributed_ytd: float,
    *,
    year: int = DEFAULT_TAX_YEAR,
    hsa_coverage: str = "self",
    limits: dict | None = None,
) -> dict:
    """Remaining tax-advantaged contribution room for the year.

    ``account_type`` is one of ``"401k"``, ``"ira"``, ``"hsa"``. Catch-up
    contributions are applied automatically by age (401k 50+ and the SECURE 2.0
    60–63 band; IRA 50+; HSA 55+).
    """
    table = limits or CONTRIBUTION_LIMITS.get(year)
    if table is None:
        return {"note": f"no contribution limits on file for {year}"}

    at = account_type.lower()
    if at == "401k":
        base = table["401k"]
        catchup = 0
        if 60 <= age <= 63:
            catchup = table["401k_catchup_60_63"]
        elif age >= 50:
            catchup = table["401k_catchup_50"]
    elif at == "ira":
        base = table["ira"]
        catchup = table["ira_catchup_50"] if age >= 50 else 0
    elif at == "hsa":
        base = table["hsa_family"] if hsa_coverage == "family" else table["hsa_self"]
        catchup = table["hsa_catchup_55"] if age >= 55 else 0
    else:
        return {"note": f"unknown account_type '{account_type}'"}

    limit = base + catchup
    remaining = max(0.0, limit - contributed_ytd)
    return {
        "account_type": at,
        "year": year,
        "annual_limit": limit,
        "base_limit": base,
        "catch_up": catchup,
        "contributed_ytd": round(contributed_ytd, 2),
        "remaining_room": round(remaining, 2),
        "remaining_monthly_to_max": round(remaining / 12, 2),
    }
