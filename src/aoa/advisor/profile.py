"""The user's financial profile — the advisor's view of *you*.

A profile is a plain, serializable snapshot of someone's personal finances. It is
the single source of truth the advisor reasons over, and it persists to JSON so a
conversation can pick up where it left off.

Nothing here talks to a brokerage or the LLM; it is pure data plus a few derived
conveniences (totals, liquidity). All judgement lives in the agent; all math
lives in :mod:`aoa.advisor.planning`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Asset categories the allocation review understands.
ASSET_CATEGORIES = ("cash", "equity", "bond", "real_estate", "crypto", "other")

# Liquid categories count toward the emergency fund.
LIQUID_CATEGORIES = ("cash",)

RISK_TOLERANCES = ("conservative", "moderate", "aggressive")


@dataclass
class FinancialAsset:
    """Something you own. ``category`` drives the allocation review."""

    name: str
    category: str  # one of ASSET_CATEGORIES
    value: float
    # Tax wrapper, if any: "taxable" | "401k" | "ira" | "roth_ira" | "hsa" | "529".
    account_type: str = "taxable"

    @property
    def is_liquid(self) -> bool:
        return self.category in LIQUID_CATEGORIES and self.account_type == "taxable"


@dataclass
class Debt:
    """Something you owe."""

    name: str
    balance: float
    apr: float  # annual rate as a decimal, e.g. 0.21 for 21%
    min_payment: float


@dataclass
class Goal:
    """A funded objective with a dollar target and a year."""

    name: str
    target_amount: float
    target_year: int
    priority: str = "medium"  # "high" | "medium" | "low"


@dataclass
class FinancialProfile:
    """A person's complete personal-finance picture."""

    name: str = "you"
    age: int = 35
    retirement_age: int = 65
    filing_status: str = "single"  # single | married_joint | married_separate | head
    state: str = ""

    # Cash flow (monthly, after-tax unless noted).
    annual_gross_income: float = 0.0
    monthly_take_home: float = 0.0
    monthly_expenses: float = 0.0
    # Non-discretionary spend used for the emergency-fund target.
    monthly_essential_expenses: float = 0.0

    # Balance sheet.
    assets: list[FinancialAsset] = field(default_factory=list)
    debts: list[Debt] = field(default_factory=list)

    # Goals.
    goals: list[Goal] = field(default_factory=list)

    # Planning assumptions.
    risk_tolerance: str = "moderate"
    expected_return: float = 0.07  # nominal annual
    inflation: float = 0.03
    safe_withdrawal_rate: float = 0.04
    emergency_fund_months_target: int = 6

    # Retirement saving (monthly contributions across all retirement accounts).
    monthly_retirement_contribution: float = 0.0
    ytd_401k_contribution: float = 0.0
    ytd_ira_contribution: float = 0.0
    ytd_hsa_contribution: float = 0.0
    hsa_coverage: str = "self"  # "self" | "family"

    notes: str = ""

    # ------------------------------------------------------------ derived views
    @property
    def total_assets(self) -> float:
        return round(sum(a.value for a in self.assets), 2)

    @property
    def total_liabilities(self) -> float:
        return round(sum(d.balance for d in self.debts), 2)

    @property
    def net_worth(self) -> float:
        return round(self.total_assets - self.total_liabilities, 2)

    @property
    def liquid_savings(self) -> float:
        return round(sum(a.value for a in self.assets if a.is_liquid), 2)

    @property
    def years_to_retirement(self) -> int:
        return max(0, self.retirement_age - self.age)

    def assets_by_category(self) -> dict[str, float]:
        out: dict[str, float] = {c: 0.0 for c in ASSET_CATEGORIES}
        for a in self.assets:
            out[a.category if a.category in out else "other"] += a.value
        return {k: round(v, 2) for k, v in out.items()}

    def completeness(self) -> list[str]:
        """Return human-readable gaps the advisor should ask about (empty == OK)."""
        missing: list[str] = []
        if self.monthly_take_home <= 0:
            missing.append("monthly take-home income")
        if self.monthly_expenses <= 0:
            missing.append("monthly expenses")
        if self.monthly_essential_expenses <= 0:
            missing.append("monthly essential (non-discretionary) expenses")
        if not self.assets:
            missing.append("assets / savings")
        return missing

    def summary(self) -> dict:
        """A compact dict the advisor sees as ground truth at the start of a chat."""
        return {
            "name": self.name,
            "age": self.age,
            "retirement_age": self.retirement_age,
            "years_to_retirement": self.years_to_retirement,
            "filing_status": self.filing_status,
            "annual_gross_income": self.annual_gross_income,
            "monthly_take_home": self.monthly_take_home,
            "monthly_expenses": self.monthly_expenses,
            "monthly_essential_expenses": self.monthly_essential_expenses,
            "net_worth": self.net_worth,
            "total_assets": self.total_assets,
            "total_liabilities": self.total_liabilities,
            "liquid_savings": self.liquid_savings,
            "assets_by_category": self.assets_by_category(),
            "debts": [asdict(d) for d in self.debts],
            "goals": [asdict(g) for g in self.goals],
            "risk_tolerance": self.risk_tolerance,
            "monthly_retirement_contribution": self.monthly_retirement_contribution,
            "missing_information": self.completeness(),
        }

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k not in ("assets", "debts", "goals")},
            "assets": [asdict(a) for a in self.assets],
            "debts": [asdict(d) for d in self.debts],
            "goals": [asdict(g) for g in self.goals],
        }

    @classmethod
    def from_dict(cls, data: dict) -> FinancialProfile:
        data = dict(data)
        assets = [FinancialAsset(**a) for a in data.pop("assets", [])]
        debts = [Debt(**d) for d in data.pop("debts", [])]
        goals = [Goal(**g) for g in data.pop("goals", [])]
        known = {f for f in cls.__dataclass_fields__}  # ignore unknown keys gracefully
        clean = {k: v for k, v in data.items() if k in known}
        return cls(assets=assets, debts=debts, goals=goals, **clean)

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> FinancialProfile:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def sample_profile() -> FinancialProfile:
    """A realistic, deliberately *imperfect* profile used for demos and tests."""
    return FinancialProfile(
        name="Alex",
        age=34,
        retirement_age=65,
        filing_status="single",
        state="CA",
        annual_gross_income=140_000,
        monthly_take_home=7_800,
        monthly_expenses=5_400,
        monthly_essential_expenses=4_200,
        assets=[
            FinancialAsset("Checking + HYSA", "cash", 18_000, "taxable"),
            FinancialAsset("Brokerage (index funds)", "equity", 62_000, "taxable"),
            FinancialAsset("401(k)", "equity", 95_000, "401k"),
            FinancialAsset("Roth IRA", "equity", 28_000, "roth_ira"),
            FinancialAsset("Bond fund", "bond", 15_000, "401k"),
        ],
        debts=[
            Debt("Credit card", 9_500, 0.224, 250),
            Debt("Student loan", 21_000, 0.058, 230),
            Debt("Auto loan", 14_000, 0.069, 410),
        ],
        goals=[
            Goal("House down payment", 120_000, 2031, "high"),
            Goal("Comfortable retirement", 2_500_000, 2057, "high"),
        ],
        risk_tolerance="moderate",
        monthly_retirement_contribution=1_500,
        ytd_401k_contribution=9_000,
        ytd_ira_contribution=2_000,
    )
