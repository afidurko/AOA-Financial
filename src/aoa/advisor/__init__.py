"""Certified financial assistant — an agentic, fiduciary personal-finance advisor.

Where :mod:`aoa.swarm` is an *autonomous trader*, this package is an *autonomous
advisor*: a CFP-style assistant that reasons over a person's whole financial
picture (cash flow, debt, emergency fund, retirement, asset allocation, and
tax-advantaged accounts) and answers questions conversationally.

The split mirrors the rest of the codebase:

- :mod:`aoa.advisor.planning` — deterministic, unit-tested financial math. No LLM.
- :mod:`aoa.advisor.profile`  — the user's financial profile (load/save JSON).
- :mod:`aoa.advisor.tools`    — the calculators exposed as Claude tools.
- :mod:`aoa.advisor.advisor`  — the agent: an agentic tool-use loop over Claude.

The model is never trusted to do arithmetic; it must *call a tool* for every
number, exactly the way the trading swarm keeps binding risk math out of the LLM.
"""

from __future__ import annotations

from aoa.advisor.advisor import FinancialAdvisor
from aoa.advisor.profile import Debt, FinancialAsset, FinancialProfile, Goal

__all__ = [
    "FinancialAdvisor",
    "FinancialProfile",
    "FinancialAsset",
    "Debt",
    "Goal",
]
