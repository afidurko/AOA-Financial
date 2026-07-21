"""Cindy — PhD company / profitability analyst with fair-value overlays."""

from __future__ import annotations

import json
import math

from aoa.agents.base import Agent, clamp_conviction
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import CompanyAnalysisReport

_SCHEMA = {
    "type": "object",
    "properties": {
        "quality_score": {"type": "number"},
        "fair_value": {"type": ["number", "null"]},
        "upside_price": {"type": ["number", "null"]},
        "downside_price": {"type": ["number", "null"]},
        "expected_return": {"type": "number"},
        "conviction": {"type": "number"},
        "thesis": {"type": "string"},
        "math_notes": {"type": "array", "items": {"type": "string"}},
        "profitability_grade": {
            "type": "string",
            "enum": ["A", "B", "C", "D", "F", "n/a"],
        },
    },
    "required": [
        "quality_score",
        "fair_value",
        "upside_price",
        "downside_price",
        "expected_return",
        "conviction",
        "thesis",
        "math_notes",
        "profitability_grade",
    ],
    "additionalProperties": False,
}

_ROLE = (
    "You are Cindy, a PhD-trained company analysis specialist on an autonomous "
    "trading team. You project profitability and fair value using advanced "
    "quantitative techniques: quality/value composites, margin and ROE inference "
    "from available metrics, risk-adjusted return estimates, and valuation bands. "
    "quality_score is in [-1,1]. expected_return is a fraction. When fundamental "
    "inputs are thin, state assumptions explicitly in math_notes and widen bands. "
    "Do not invent audited financials that are not present."
)


class CindyAgent(Agent):
    name = "cindy"
    display_name = "Cindy"
    role = "Company Profitability Analyst"

    system_prompt = _ROLE

    def analyze_contexts(
        self, snapshots: dict[str, SymbolSnapshot]
    ) -> list[CompanyAnalysisReport]:
        return [self.analyze_symbol(snap) for snap in snapshots.values()]

    def analyze_symbol(self, snap: SymbolSnapshot) -> CompanyAnalysisReport:
        if snap.error:
            return CompanyAnalysisReport(
                symbol=snap.symbol,
                quality_score=0.0,
                fair_value=None,
                upside_price=None,
                downside_price=None,
                expected_return=0.0,
                conviction=0.0,
                thesis=f"No market data ({snap.error}).",
                math_notes=["Insufficient data for profitability projection."],
            )

        quant = compute_profitability_quant(snap)
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Quote: {json.dumps(snap.to_context().get('quote'), default=str)}\n"
            f"Technicals: {json.dumps(snap.technicals, default=str)}\n"
            f"Deterministic quant scaffold:\n{json.dumps(quant, default=str)}\n\n"
            "Produce a company profitability / fair-value analysis as JSON. "
            "Prefer anchoring fair_value and bands near the quant scaffold "
            "unless you have a clear reason to adjust."
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        fair = _opt_float(r.get("fair_value"))
        if fair is None:
            fair = quant.get("fair_value")
        upside = _opt_float(r.get("upside_price")) or quant.get("upside_price")
        downside = _opt_float(r.get("downside_price")) or quant.get("downside_price")
        notes = [str(n) for n in (r.get("math_notes") or [])]
        for n in quant.get("notes") or []:
            if n not in notes:
                notes.append(n)
        return CompanyAnalysisReport(
            symbol=snap.symbol,
            quality_score=_clamp_score(r.get("quality_score", quant.get("quality_score", 0.0))),
            fair_value=fair,
            upside_price=upside,
            downside_price=downside,
            expected_return=float(r.get("expected_return") or quant.get("expected_return", 0.0)),
            conviction=clamp_conviction(r.get("conviction", quant.get("conviction", 0.0))),
            thesis=str(r.get("thesis", "")),
            math_notes=notes,
            components=dict(quant.get("components") or {}),
            profitability_grade=str(r.get("profitability_grade") or quant.get("grade", "n/a")),
        )


def compute_profitability_quant(snap: SymbolSnapshot) -> dict:
    """Deterministic profitability / fair-value scaffold from price history."""
    closes = _closes(snap)
    last = snap.reference_price() or (closes[-1] if closes else None)
    notes: list[str] = []
    components: dict[str, float] = {}
    if last is None or last <= 0 or len(closes) < 5:
        notes.append("Thin history — using neutral quality prior.")
        return {
            "quality_score": 0.0,
            "fair_value": last,
            "upside_price": round(last * 1.05, 4) if last else None,
            "downside_price": round(last * 0.95, 4) if last else None,
            "expected_return": 0.0,
            "conviction": 0.2,
            "components": components,
            "notes": notes,
            "grade": "n/a",
        }

    # Trend regression on log prices → implied fair and horizon return.
    logp = [math.log(c) for c in closes if c > 0]
    n = len(logp)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(logp) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, logp, strict=True))
    den = sum((x - x_mean) ** 2 for x in xs) or 1.0
    slope = num / den
    intercept = y_mean - slope * x_mean
    fair = math.exp(intercept + slope * (n - 1))
    # 10-bar projected return from trend slope.
    proj = math.exp(intercept + slope * (n - 1 + 10))
    expected = (proj / last) - 1.0

    # Momentum + mean-reversion components as profitability proxies when
    # audited fundamentals are unavailable.
    mom20 = (closes[-1] / closes[-min(20, n)]) - 1.0
    rets = [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, n)
        if closes[i - 1] > 0
    ]
    vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 if rets else 0.02
    sharpe_like = (sum(rets) / len(rets)) / vol if vol > 1e-9 else 0.0

    components["trend_fair_gap"] = _clamp_score((fair / last) - 1.0)
    components["momentum_20"] = _clamp_score(mom20 / 0.08)
    components["risk_adj_drift"] = _clamp_score(sharpe_like / 0.5)
    quality = sum(components.values()) / max(1, len(components))
    notes.append(
        f"OLS log-price fair≈{fair:.2f} vs mark {last:.2f}; "
        f"10-bar trend return≈{expected:+.2%}."
    )
    notes.append(
        f"Momentum20={mom20:+.2%}, vol≈{vol:.3f}, sharpe-like={sharpe_like:.2f}."
    )
    band = max(0.03, min(0.18, 2.5 * vol * math.sqrt(10)))
    upside = last * (1.0 + max(band, expected + band * 0.5))
    downside = last * (1.0 - band)
    grade = _grade(quality)
    conviction = clamp_conviction(0.35 + 0.4 * abs(quality))
    return {
        "quality_score": round(quality, 3),
        "fair_value": round(fair, 4),
        "upside_price": round(upside, 4),
        "downside_price": round(downside, 4),
        "expected_return": round(expected, 4),
        "conviction": conviction,
        "components": {k: round(v, 3) for k, v in components.items()},
        "notes": notes,
        "grade": grade,
    }


def _closes(snap: SymbolSnapshot) -> list[float]:
    bars = snap.bars or snap.bars_by_timeframe.get("1Day") or []
    out = [float(b.close) for b in bars if getattr(b, "close", None)]
    if out:
        return out
    last = snap.last_close()
    return [float(last)] if last else []


def _opt_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clamp_score(v) -> float:
    try:
        return max(-1.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _grade(quality: float) -> str:
    if quality >= 0.55:
        return "A"
    if quality >= 0.25:
        return "B"
    if quality >= -0.1:
        return "C"
    if quality >= -0.4:
        return "D"
    return "F"
