"""News analyst — macro and company news events (TradingAgents analyst team)."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, Direction, Signal, clamp_conviction, parse_direction
from aoa.data.market_data import SymbolSnapshot
from aoa.data.news import NewsItem
from aoa.llm.client import LLMError

_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "conviction": {"type": "number"},
        "summary": {"type": "string"},
        "key_events": {"type": "array", "items": {"type": "string"}},
        "macro_risk": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["direction", "conviction", "summary", "key_events", "macro_risk"],
    "additionalProperties": False,
}


class NewsAnalystAgent(Agent):
    name = "news"
    system_prompt = (
        "You are the news analyst on a trading firm's analyst team. Analyze verified "
        "headlines and macro context for market-moving events. Produce a structured "
        "report with direction, conviction, a concise summary, and key_events bullets. "
        "Never fabricate headlines — if none are provided, assess macro risk qualitatively "
        "and lean neutral."
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
                "\nVerified headlines:\n"
                + json.dumps([h.to_context() for h in headlines], default=str)
                + "\n"
            )
        quote_ctx = {}
        if snap.quote:
            quote_ctx = {"bid": snap.quote.bid, "ask": snap.quote.ask, "mid": snap.quote.mid}
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Quote context: {json.dumps(quote_ctx, default=str)}\n"
            f"{news_block}\n"
            "Return structured news analysis as JSON."
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
        events = list(r.get("key_events") or [])
        summary = r.get("summary", "")
        return Signal(
            symbol=snap.symbol,
            source=self.name,
            direction=parse_direction(r.get("direction")),
            conviction=clamp_conviction(r.get("conviction")),
            rationale=summary or "News analysis complete.",
            tags=["news", f"macro_risk:{r.get('macro_risk', 'medium')}", *[f"event:{e[:40]}" for e in events[:3]]],
        )
