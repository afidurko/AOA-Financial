"""Alan — aggregates Tom and Julie's work into decision-ready briefs."""

from __future__ import annotations

import json

from aoa.agents.base import Agent
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
                    "action": {"type": "string", "enum": ["watch", "consider_long", "consider_short_exit", "avoid"]},
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
    role = "Decision Aggregator"

    system_prompt = (
        "You are Alan, the decision aggregator on an autonomous trading team. You "
        "receive Tom's trend reports and Julie's algorithmic validations. Synthesize "
        "them into a focused decision brief: per-symbol recommendations "
        "(watch, consider_long, consider_short_exit, avoid), conviction in [0,1], "
        "and a team-level summary with overall confidence. This is a CASH account — "
        "no shorting. Prioritize names where Tom and Julie agree with high strength. "
        "When they conflict or data is weak, recommend watch or avoid."
    )

    def aggregate(
        self,
        trends: list[TrendReport],
        algorithms: list[AlgorithmReport],
        *,
        scanner_context: list[dict] | None = None,
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
        prompt = (
            f"Trend + algorithm pairs:\n{json.dumps(pairs, default=str)}\n"
        )
        if scanner_context:
            prompt += f"\nScanner shortlist context:\n{json.dumps(scanner_context, default=str)}\n"
        prompt += "\nProduce the aggregated decision brief as JSON."
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        return DecisionBrief(
            recommendations=list(r.get("recommendations") or []),
            summary=r.get("summary", ""),
            confidence=_clamp(r.get("confidence", 0.5)),
        )


def _clamp(v: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
