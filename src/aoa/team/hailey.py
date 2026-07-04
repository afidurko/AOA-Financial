"""Hailey — news and catalyst analyst for the team layer."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, clamp_conviction
from aoa.data.market_data import SymbolSnapshot
from aoa.data.news import NewsFeed, NewsItem, NullNewsFeed
from aoa.team.models import CatalystReport

_SCHEMA = {
    "type": "object",
    "properties": {
        "catalyst_summary": {"type": "string"},
        "event_risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "headline_sentiment": {
            "type": "string",
            "enum": ["bullish", "bearish", "neutral"],
        },
        "key_events": {"type": "array", "items": {"type": "string"}},
        "macro_note": {"type": "string"},
        "impact_score": {"type": "number"},
    },
    "required": [
        "catalyst_summary",
        "event_risk",
        "headline_sentiment",
        "key_events",
        "macro_note",
        "impact_score",
    ],
    "additionalProperties": False,
}


class HaileyAgent(Agent):
    name = "hailey"
    display_name = "Hailey"
    role = "News & Catalyst Analyst"

    system_prompt = (
        "You are Hailey, the news and catalyst analyst on an autonomous trading team. "
        "Given verified headlines and symbol context, explain WHY a name may be moving, "
        "flag upcoming event risk (earnings, FDA, macro, legal), and assess headline "
        "sentiment. Never invent headlines not present in the input. If no news is "
        "available, note that and assess macro risk qualitatively. impact_score is "
        "0.0–1.0 for how much catalysts should influence trading decisions today."
    )

    def __init__(self, llm, news: NewsFeed | None = None) -> None:
        super().__init__(llm)
        self.news = news or NullNewsFeed()

    def analyze_contexts(
        self, snapshots: dict[str, SymbolSnapshot]
    ) -> list[CatalystReport]:
        symbols = [snap.symbol for snap in snapshots.values()]
        headlines_by = self.news.headlines(symbols, limit=5)
        return [
            self.analyze_symbol(snap, headlines_by.get(snap.symbol.upper(), []))
            for snap in snapshots.values()
        ]

    def analyze_symbol(
        self,
        snap: SymbolSnapshot,
        headlines: list[NewsItem] | None = None,
    ) -> CatalystReport:
        if snap.error:
            return CatalystReport(
                symbol=snap.symbol,
                catalyst_summary=f"No market data ({snap.error}).",
                event_risk="high",
                headline_sentiment="neutral",
                macro_note="Cannot assess catalysts without price data.",
            )

        news_block = ""
        if headlines:
            news_block = (
                "\nVerified headlines:\n"
                + json.dumps([h.to_context() for h in headlines], default=str)
                + "\n"
            )
        else:
            news_block = "\nNo verified headlines in lookback window.\n"

        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Quote context: {json.dumps(snap.to_context().get('quote'), default=str)}\n"
            f"{news_block}\n"
            "Return catalyst analysis as JSON."
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        return CatalystReport(
            symbol=snap.symbol,
            catalyst_summary=str(r.get("catalyst_summary", "")),
            event_risk=str(r.get("event_risk", "medium")),
            headline_sentiment=str(r.get("headline_sentiment", "neutral")),
            key_events=[str(e) for e in (r.get("key_events") or [])],
            macro_note=str(r.get("macro_note", "")),
            impact_score=clamp_conviction(r.get("impact_score", 0.0)),
        )
