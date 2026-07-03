"""Julie — algorithm specialist who refines Tom's trend analysis."""

from __future__ import annotations

import json

from aoa.agents.base import Agent
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import AlgorithmReport, TrendReport

_SCHEMA = {
    "type": "object",
    "properties": {
        "validated": {"type": "boolean"},
        "adjusted_strength": {"type": "number"},
        "method_notes": {"type": "string"},
        "signals": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["validated", "adjusted_strength", "method_notes", "signals"],
    "additionalProperties": False,
}


class JulieAgent(Agent):
    name = "julie"
    display_name = "Julie"
    role = "Algorithm Specialist"

    system_prompt = (
        "You are Julie, the algorithm specialist on an autonomous trading team. You "
        "work with Tom's trend read and the raw indicator data to validate or "
        "challenge it using quantitative methods: moving-average crossovers, RSI "
        "regime, MACD histogram slope, Bollinger band position, ATR-normalized "
        "moves, and short-horizon return consistency. Output whether Tom's trend "
        "call is algorithmically validated, an adjusted strength in [0,1], concise "
        "method notes, and named signals that support or contradict the trend."
    )

    def refine(
        self,
        trend: TrendReport,
        snap: SymbolSnapshot,
    ) -> AlgorithmReport:
        if snap.error or not snap.technicals:
            return AlgorithmReport(
                symbol=trend.symbol,
                validated=False,
                adjusted_strength=0.0,
                method_notes="Insufficient data for algorithmic validation.",
            )
        prompt = (
            f"Tom's trend report:\n{json.dumps(trend.to_context())}\n\n"
            f"Symbol: {snap.symbol}\n"
            f"Technicals: {json.dumps(snap.technicals, default=str)}\n\n"
            "Validate and refine Tom's trend read. Return JSON."
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        return AlgorithmReport(
            symbol=trend.symbol,
            validated=bool(r.get("validated")),
            adjusted_strength=_clamp(r.get("adjusted_strength", 0)),
            method_notes=r.get("method_notes", ""),
            signals=list(r.get("signals") or []),
        )


def _clamp(v: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
