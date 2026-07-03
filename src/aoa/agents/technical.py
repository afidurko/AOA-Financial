"""Technical analyst agent — produces a directional signal from indicators."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, Direction, Signal
from aoa.data.market_data import SymbolSnapshot

_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "conviction": {"type": "number"},
        "horizon": {"type": "string", "enum": ["intraday", "swing", "position"]},
        "rationale": {"type": "string"},
        "support": {"type": "number"},
        "resistance": {"type": "number"},
        "stop_suggestion": {"type": "number"},
    },
    "required": ["direction", "conviction", "horizon", "rationale"],
    "additionalProperties": False,
}


class TechnicalAgent(Agent):
    name = "technical"
    system_prompt = (
        "You are a technical analyst. Given a symbol's price action and indicators "
        "(SMA/EMA stack, RSI, MACD, Bollinger bands, ATR, realized volatility, "
        "recent returns), produce a single directional read with a calibrated "
        "conviction in [0,1]. Be honest: most setups are neutral. Reserve high "
        "conviction (>0.7) for genuinely clean, confluent setups. Identify nearby "
        "support/resistance and a sensible stop based on ATR. Do not invent data "
        "that is not present."
    )

    def analyze(self, snap: SymbolSnapshot) -> Signal:
        if snap.error or not snap.technicals:
            return Signal(
                symbol=snap.symbol,
                source=self.name,
                direction=Direction.NEUTRAL,
                conviction=0.0,
                rationale=f"No usable technical data ({snap.error or 'empty'}).",
            )
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Quote: {json.dumps(snap.to_context()['quote'])}\n"
            f"Technicals: {json.dumps(snap.technicals, default=str)}\n\n"
            "Return your technical read as JSON."
        )
        r = self.structured_safe(
            self.system_prompt,
            prompt,
            _SCHEMA,
            {
                "direction": "neutral",
                "conviction": 0.0,
                "horizon": "swing",
                "rationale": "LLM unavailable; defaulting to neutral.",
            },
        )
        levels = {}
        if r.get("support") is not None:
            levels["support"] = r["support"]
        if r.get("resistance") is not None:
            levels["resistance"] = r["resistance"]
        if r.get("stop_suggestion") is not None:
            levels["stop"] = r["stop_suggestion"]
        try:
            direction = Direction(r.get("direction", "neutral"))
        except ValueError:
            direction = Direction.NEUTRAL
        return Signal(
            symbol=snap.symbol,
            source=self.name,
            direction=direction,
            conviction=_clamp(r.get("conviction", 0.0)),
            rationale=r.get("rationale", "No rationale provided."),
            horizon=r.get("horizon", "swing"),
            key_levels=levels,
            tags=["technical"],
        )


def _clamp(v: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
