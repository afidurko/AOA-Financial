"""Alan — aggregates Tom, Julie, Bob, and code-quality into decision briefs."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, clamp_conviction
from aoa.team.code_engineering import CodeQualityReport
from aoa.team.models import AlgorithmReport, DecisionBrief, TrendReport

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
        "receive Tom's trend reports, Julie's algorithmic validations, and Bob's "
        "code-quality audits. Synthesize them into a focused decision brief: "
        "per-symbol recommendations (watch, consider_long, consider_short_exit, "
        "avoid), conviction in [0,1], and a team-level summary with overall "
        "confidence. This is a CASH account — no shorting. Prioritize names where "
        "Tom and Julie agree with high strength. When code quality is degraded or "
        "critical, lower confidence and prefer watch/avoid until Bob's issues are "
        "resolved. When they conflict or data is weak, recommend watch or avoid."
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
    ) -> DecisionBrief:
        by_symbol = {a.symbol: a for a in algorithms}
        pairs = [
            {
                "symbol": t.symbol,
                "trend": t.to_context(),
                "algorithm": by_symbol.get(t.symbol, {}).to_context()
                if t.symbol in by_symbol
                else None,
            }
            for t in trends
        ]
        prompt = f"Trend + algorithm pairs:\n{json.dumps(pairs, default=str)}\n"
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
        prompt += "\nProduce the aggregated decision brief as JSON."
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        confidence = clamp_conviction(r.get("confidence", 0.5), default=0.5)
        if code_quality and not code_quality.can_proceed:
            confidence = min(confidence, 0.25)
        elif code_quality and code_quality.worst_status.value == "degraded":
            confidence = min(confidence, 0.55)
        return DecisionBrief(
            recommendations=list(r.get("recommendations") or []),
            summary=r.get("summary", ""),
            confidence=confidence,
            code_quality=code_quality.to_context() if code_quality else None,
        )
