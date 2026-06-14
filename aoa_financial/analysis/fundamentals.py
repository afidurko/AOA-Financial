"""Fundamental scoring.

Turns a raw fundamentals dict into a normalised [-1, 1] quality/value score
with a human-readable breakdown, so both the fundamental agent and the LLM
analyst can reason about *why* a name screens well or poorly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class FundamentalScore:
    composite: float                      # [-1, 1]
    components: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"composite": self.composite, "components": self.components,
                "notes": self.notes}


def score(fund: Optional[Dict[str, float]]) -> FundamentalScore:
    if not fund:
        return FundamentalScore(0.0, {}, ["no fundamental data available"])

    comp: Dict[str, float] = {}
    notes: List[str] = []

    pe = fund.get("pe_ratio")
    if pe is not None:
        # Cheap (low PE) is good; map ~15 -> neutral, <10 strong, >35 poor.
        comp["valuation_pe"] = _clamp((22.0 - pe) / 18.0)
        if pe < 10:
            notes.append(f"low P/E ({pe:.1f}) — potential value")
        elif pe > 35:
            notes.append(f"elevated P/E ({pe:.1f}) — growth priced in")

    pb = fund.get("pb_ratio")
    if pb is not None:
        comp["valuation_pb"] = _clamp((3.0 - pb) / 3.0)

    g = fund.get("revenue_growth")
    if g is not None:
        comp["growth"] = _clamp(g / 0.25)
        if g > 0.2:
            notes.append(f"strong revenue growth ({g:+.0%})")
        elif g < 0:
            notes.append(f"revenue contracting ({g:+.0%})")

    m = fund.get("profit_margin")
    if m is not None:
        comp["profitability"] = _clamp(m / 0.2)

    roe = fund.get("roe")
    if roe is not None:
        comp["roe"] = _clamp(roe / 0.2)
        if roe > 0.2:
            notes.append(f"high ROE ({roe:.0%})")

    de = fund.get("debt_to_equity")
    if de is not None:
        # Lower leverage is safer; 1.0 neutral-ish, >2 penalised.
        comp["leverage"] = _clamp((1.0 - de) / 1.5)
        if de > 2.0:
            notes.append(f"high leverage (D/E {de:.1f})")

    fcf = fund.get("free_cash_flow")
    if fcf is not None:
        comp["cash_flow"] = _clamp(fcf / 2.0)

    dy = fund.get("dividend_yield")
    if dy is not None and dy > 0.03:
        comp["income"] = _clamp(dy / 0.05)
        notes.append(f"meaningful dividend yield ({dy:.1%})")

    # Weighted composite. Quality (profitability/roe/cash) and value share
    # billing; growth is a smaller tilt.
    weights = {
        "valuation_pe": 0.18, "valuation_pb": 0.10, "growth": 0.16,
        "profitability": 0.16, "roe": 0.14, "leverage": 0.12,
        "cash_flow": 0.10, "income": 0.04,
    }
    num = sum(comp[k] * w for k, w in weights.items() if k in comp)
    den = sum(w for k, w in weights.items() if k in comp)
    composite = _clamp(num / den) if den else 0.0
    return FundamentalScore(round(composite, 4),
                            {k: round(v, 4) for k, v in comp.items()}, notes)
