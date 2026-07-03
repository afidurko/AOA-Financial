"""Fundamental / catalyst agent.

Uses live headlines from the broker's Alpaca news feed when available. The agent
is instructed to cite only headlines present in its prompt and never fabricate
news it cannot verify.
"""

from __future__ import annotations

import json

from aoa.agents.base import Agent, Direction, Signal
from aoa.brokerage.models import NewsItem
from aoa.data.market_data import SymbolSnapshot

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
        "You are a fundamental & catalyst analyst supporting a trading swarm. You "
        "may receive verified news headlines from an Alpaca news feed. Only cite "
        "headlines that appear in the provided news context — never invent specific "
        "headlines, earnings dates, or numbers. Combine news with structural "
        "context (sector posture, character of the recent move) and flag elevated "
        "event risk so the risk manager can size conservatively. When news is "
        "absent or inconclusive, say so and lean neutral."
    )

    def analyze(self, snap: SymbolSnapshot, *, news: list[NewsItem] | None = None) -> Signal:
        if snap.error:
            return Signal(
                symbol=snap.symbol,
                source=self.name,
                direction=Direction.NEUTRAL,
                conviction=0.0,
                rationale=f"No data ({snap.error}).",
            )
        news_ctx = [item.to_context() for item in (news or [])]
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Recent technical context: {json.dumps(snap.technicals, default=str)}\n"
            f"Verified news headlines (may be empty): {json.dumps(news_ctx, default=str)}\n\n"
            "Give your qualitative fundamental/catalyst read and event-risk "
            "assessment as JSON. Cite only headlines from the news context above."
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        return Signal(
            symbol=snap.symbol,
            source=self.name,
            direction=Direction(r["direction"]),
            conviction=max(0.0, min(1.0, float(r["conviction"]))),
            rationale=r["rationale"],
            tags=["fundamental", f"event_risk:{r.get('event_risk', 'medium')}"],
        )
