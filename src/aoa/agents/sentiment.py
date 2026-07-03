"""Sentiment analyst — market sentiment from headline tone (TradingAgents analyst team)."""

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
        "sentiment_score": {"type": "number"},
        "summary": {"type": "string"},
        "drivers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["direction", "conviction", "sentiment_score", "summary", "drivers"],
    "additionalProperties": False,
}


class SentimentAnalystAgent(Agent):
    name = "sentiment"
    system_prompt = (
        "You are the sentiment analyst on a trading firm's analyst team. Infer "
        "short-term market sentiment toward a symbol from verified headline tone "
        "and price/volume context. Return sentiment_score in [-1, 1] (bearish to "
        "bullish), direction, conviction, summary, and drivers. Do not invent "
        "social posts — use only provided headlines as a sentiment proxy."
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
                "\nHeadlines for sentiment read:\n"
                + json.dumps([h.to_context() for h in headlines], default=str)
                + "\n"
            )
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Technicals snippet: {json.dumps(snap.technicals, default=str)}\n"
            f"{news_block}\n"
            "Return structured sentiment analysis as JSON."
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
            rationale=r.get("summary", "Sentiment analysis complete."),
            tags=[
                "sentiment",
                f"score:{float(r.get('sentiment_score', 0)):+.2f}",
            ],
        )
