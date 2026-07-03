"""Fundamental / catalyst agent.

Without a paid news feed this agent reasons about *known structural context* and
*event risk* (e.g. proximity to typical earnings windows, sector posture, and the
character of the recent move) rather than fabricating headlines. It is explicitly
instructed never to invent specific news it cannot verify. If a news/web-search
tool is wired in later, this agent's prompt is the natural integration point.
"""

from __future__ import annotations

import json

from aoa.agents.base import Agent, Direction, Signal, clamp_conviction, parse_direction
from aoa.data.market_data import SymbolSnapshot
from aoa.llm.client import LLMError

_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "conviction": {"type": "number"},
        "event_risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string"},
    },
    "required": ["direction", "conviction", "event_risk", "rationale"],
    "additionalProperties": False,
}


class FundamentalAgent(Agent):
    name = "fundamental"
    system_prompt = (
        "You are a fundamental & catalyst analyst supporting a trading swarm. You do "
        "NOT have a live news feed, so you must NOT invent specific headlines, "
        "earnings dates, or numbers. Instead, reason qualitatively about structural "
        "context: the company's sector and its current posture, the character of the "
        "recent price move (trend vs spike), and general event risk (e.g. that "
        "single-stock names carry earnings/guidance risk that broad ETFs do not). "
        "Flag elevated event risk so the risk manager can size conservatively. When "
        "you lack information, say so and lean neutral."
    )

    def analyze(self, snap: SymbolSnapshot) -> Signal:
        if snap.error:
            return Signal(
                symbol=snap.symbol,
                source=self.name,
                direction=Direction.NEUTRAL,
                conviction=0.0,
                rationale=f"No data ({snap.error}).",
            )
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Recent technical context: {json.dumps(snap.technicals, default=str)}\n\n"
            "Give your qualitative fundamental/catalyst read and event-risk "
            "assessment as JSON. Remember: do not fabricate specific news."
        )
        try:
            r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        except LLMError as exc:
            return Signal(
                symbol=snap.symbol,
                source=self.name,
                direction=Direction.NEUTRAL,
                conviction=0.0,
                rationale=f"LLM unavailable ({exc}).",
            )
        return Signal(
            symbol=snap.symbol,
            source=self.name,
            direction=parse_direction(r.get("direction")),
            conviction=clamp_conviction(r.get("conviction")),
            rationale=r.get("rationale", "No rationale provided."),
            tags=["fundamental", f"event_risk:{r.get('event_risk', 'medium')}"],
        )
