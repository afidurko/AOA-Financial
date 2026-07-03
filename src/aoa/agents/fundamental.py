"""Fundamental / catalyst agent.

When a news feed is wired in, this agent incorporates verified recent headlines
from Alpaca into its catalyst read. Without headlines it reasons about known
structural context and event risk rather than fabricating news.
"""

from __future__ import annotations

import json

from aoa.agents.base import Agent, Direction, Signal
from aoa.data.market_data import SymbolSnapshot
from aoa.data.news import NewsItem

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
        "You are a fundamental & catalyst analyst supporting a trading swarm. "
        "When recent verified headlines are provided, use them to assess catalysts "
        "and event risk. When no headlines are provided, you must NOT invent "
        "specific headlines, earnings dates, or numbers — instead reason "
        "qualitatively about structural context: sector posture, the character "
        "of the recent price move, and general event risk. Flag elevated event "
        "risk so the risk manager can size conservatively. When you lack "
        "information, say so and lean neutral."
    )

    def analyze(
        self,
        snap: SymbolSnapshot,
        *,
        headlines: list[NewsItem] | None = None,
    ) -> Signal:
        if snap.error:
            return Signal(
                symbol=snap.symbol,
                source=self.name,
                direction=Direction.NEUTRAL,
                conviction=0.0,
                rationale=f"No data ({snap.error}).",
            )
        news_block = ""
        if headlines:
            news_block = (
                "\nRecent verified headlines:\n"
                + json.dumps([h.to_context() for h in headlines], default=str)
                + "\n"
            )
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Recent technical context: {json.dumps(snap.technicals, default=str)}\n"
            f"{news_block}\n"
            "Give your qualitative fundamental/catalyst read and event-risk "
            "assessment as JSON."
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
