"""Julie — algorithm specialist and code-clarity reviewer."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, clamp_conviction
from aoa.data.market_data import SymbolSnapshot
from aoa.team.code_engineering import CodeQualityReport, run_code_quality_audit
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
    role = "Algorithm Specialist & Code Clarity"

    system_prompt = (
        "You are Julie, the algorithm specialist on an autonomous trading team. You "
        "work with Tom's trend read and the raw indicator data to validate or "
        "challenge it using quantitative methods: moving-average crossovers, RSI "
        "regime, MACD histogram slope, Bollinger band position, ATR-normalized "
        "moves, and short-horizon return consistency. You also keep the codebase "
        "clean — flag duplicated helpers, fragile patterns, and unclear logic in "
        "your method notes when Bob's code audit surfaces issues. Output whether "
        "Tom's trend call is algorithmically validated, an adjusted strength in "
        "[0,1], concise method notes, and named signals that support or contradict "
        "the trend."
    )

    def audit_codebase(self) -> CodeQualityReport:
        """Run the same deterministic sweep Bob uses — Julie validates clarity."""
        return run_code_quality_audit()

    def refine(
        self,
        trend: TrendReport,
        snap: SymbolSnapshot,
        *,
        code_quality: CodeQualityReport | None = None,
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
            f"Technicals: {json.dumps(snap.technicals, default=str)}\n"
        )
        if code_quality is not None:
            prompt += (
                f"\nBob's code-quality audit:\n"
                f"{json.dumps(code_quality.to_context(), default=str)}\n"
            )
        prompt += "\nValidate and refine Tom's trend read. Return JSON."
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        notes = r.get("method_notes", "")
        if code_quality and code_quality.worst_status.value != "ok":
            notes = f"{notes} Code note: {code_quality.summary}".strip()
        return AlgorithmReport(
            symbol=trend.symbol,
            validated=bool(r.get("validated")),
            adjusted_strength=clamp_conviction(r.get("adjusted_strength", 0)),
            method_notes=notes,
            signals=list(r.get("signals") or []),
        )
