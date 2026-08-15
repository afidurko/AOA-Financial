"""Alan — aggregates Tom, Julie, Jim, Cindy, Bob, and code-quality into briefs."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, clamp_conviction
from aoa.team.code_engineering import CodeQualityReport
from aoa.team.models import (
    AlgorithmReport,
    CompanyAnalysisReport,
    DecisionBrief,
    ShortTermReport,
    TrendReport,
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["watch", "consider_long", "consider_short_exit", "avoid"],
                    },
                    "conviction": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["symbol", "action", "conviction", "rationale"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["recommendations", "summary", "confidence"],
    "additionalProperties": False,
}


class AlanAgent(Agent):
    name = "alan"
    display_name = "Alan"
    role = "Decision Aggregator & Code Oversight"

    system_prompt = (
        "You are Alan, the decision aggregator on an autonomous trading team. You "
        "receive Tom's trend reports, Julie's algorithmic validations, Jim's "
        "short-term technical predictions, Cindy's company profitability / "
        "fair-value analysis, and Bob's code-quality audits. Synthesize them into "
        "a focused decision brief: per-symbol recommendations (watch, "
        "consider_long, consider_short_exit, avoid), conviction in [0,1], and a "
        "team-level summary with overall confidence. This is a CASH account — no "
        "shorting. Adapt conviction using Jim's near-term path and Cindy's "
        "quality/fair-value bands: raise conviction when they corroborate Tom/"
        "Julie; lower or prefer watch when Jim's path conflicts with Cindy's "
        "fair-value gap or when code quality is degraded/critical. When they "
        "conflict or data is weak, recommend watch or avoid."
    )

    def aggregate(
        self,
        trends: list[TrendReport],
        algorithms: list[AlgorithmReport],
        *,
        scanner_context: list[dict] | None = None,
        code_quality: CodeQualityReport | None = None,
        market_contexts: list | None = None,
        catalyst_contexts: list | None = None,
        short_term_contexts: list[ShortTermReport] | None = None,
        company_contexts: list[CompanyAnalysisReport] | None = None,
    ) -> DecisionBrief:
        by_symbol = {a.symbol: a for a in algorithms}
        jim_by = {j.symbol: j for j in (short_term_contexts or [])}
        cindy_by = {c.symbol: c for c in (company_contexts or [])}
        pairs = [
            {
                "symbol": t.symbol,
                "trend": t.to_context(),
                "algorithm": by_symbol.get(t.symbol, {}).to_context()
                if t.symbol in by_symbol
                else None,
                "jim_short_term": jim_by[t.symbol].to_context()
                if t.symbol in jim_by
                else None,
                "cindy_company": cindy_by[t.symbol].to_context()
                if t.symbol in cindy_by
                else None,
            }
            for t in trends
        ]
        prompt = f"Trend + algorithm pairs (with Jim/Cindy):\n{json.dumps(pairs, default=str)}\n"
        if scanner_context:
            prompt += f"\nScanner shortlist context:\n{json.dumps(scanner_context, default=str)}\n"
        if code_quality is not None:
            prompt += (
                f"\nBob/Julie code-quality audit:\n"
                f"{json.dumps(code_quality.to_context(), default=str)}\n"
            )
        if market_contexts:
            prompt += (
                f"\nMorgan market/volume context:\n"
                f"{json.dumps([m.to_context() for m in market_contexts], default=str)}\n"
            )
        if catalyst_contexts:
            prompt += (
                f"\nHailey news/catalyst context:\n"
                f"{json.dumps([c.to_context() for c in catalyst_contexts], default=str)}\n"
            )
        if short_term_contexts:
            prompt += (
                f"\nJim short-term technical overlays:\n"
                f"{json.dumps([j.to_context() for j in short_term_contexts], default=str)}\n"
            )
        if company_contexts:
            prompt += (
                f"\nCindy company profitability analysis:\n"
                f"{json.dumps([c.to_context() for c in company_contexts], default=str)}\n"
            )
        prompt += (
            "\nProduce the aggregated decision brief as JSON. Partially adapt "
            "actions and conviction from Jim's predicted path and Cindy's "
            "fair-value / quality work."
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        confidence = clamp_conviction(r.get("confidence", 0.5), default=0.5)
        if code_quality and not code_quality.can_proceed:
            confidence = min(confidence, 0.25)
        elif code_quality and code_quality.worst_status.value == "degraded":
            confidence = min(confidence, 0.55)
        recommendations = _adapt_recommendations(
            list(r.get("recommendations") or []),
            short_term_contexts or [],
            company_contexts or [],
        )
        return DecisionBrief(
            recommendations=recommendations,
            summary=r.get("summary", ""),
            confidence=confidence,
            code_quality=code_quality.to_context() if code_quality else None,
        )


def _adapt_recommendations(
    recommendations: list[dict],
    short_term: list[ShortTermReport],
    company: list[CompanyAnalysisReport],
) -> list[dict]:
    """Deterministic partial adaptation of Alan's LLM brief using Jim/Cindy."""
    jim_by = {j.symbol.upper(): j for j in short_term}
    cindy_by = {c.symbol.upper(): c for c in company}
    out: list[dict] = []
    for rec in recommendations:
        item = dict(rec)
        sym = str(item.get("symbol") or "").upper()
        if not sym:
            out.append(item)
            continue
        jim = jim_by.get(sym)
        cindy = cindy_by.get(sym)
        conv = clamp_conviction(item.get("conviction", 0.5), default=0.5)
        notes: list[str] = []
        if jim and cindy:
            jim_bull = jim.direction.value == "up" and jim.expected_return >= 0
            jim_bear = jim.direction.value == "down" or jim.expected_return < 0
            cindy_cheap = (
                cindy.fair_value is not None
                and cindy.expected_return >= 0
                and cindy.quality_score >= 0
            )
            cindy_rich = cindy.quality_score < 0 or (
                cindy.fair_value is not None and cindy.expected_return < 0
            )
            if jim_bull and cindy_cheap:
                conv = min(1.0, conv + 0.08 * jim.conviction + 0.06 * cindy.conviction)
                notes.append("Jim+Cindy corroboration (+)")
            elif jim_bear and cindy_rich:
                conv = max(0.0, conv - 0.1)
                if item.get("action") == "consider_long":
                    item["action"] = "watch"
                notes.append("Jim+Cindy caution (−)")
            elif jim_bull and cindy_rich:
                conv = max(0.0, conv - 0.05)
                notes.append("Jim bullish vs Cindy rich — tempered")
            elif jim_bear and cindy_cheap:
                conv = max(0.0, conv - 0.04)
                notes.append("Jim weak near-term vs Cindy value — tempered")
        elif jim:
            if jim.direction.value == "up":
                conv = min(1.0, conv + 0.04 * jim.conviction)
            elif jim.direction.value == "down":
                conv = max(0.0, conv - 0.05 * jim.conviction)
        elif cindy:
            if cindy.quality_score > 0.25:
                conv = min(1.0, conv + 0.04 * cindy.conviction)
            elif cindy.quality_score < -0.25:
                conv = max(0.0, conv - 0.05 * cindy.conviction)
        item["conviction"] = round(conv, 2)
        if notes:
            rationale = str(item.get("rationale") or "")
            suffix = "; ".join(notes)
            item["rationale"] = f"{rationale} [{suffix}]".strip()
        out.append(item)
    return out
