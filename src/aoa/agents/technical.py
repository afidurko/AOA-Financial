"""Technical analyst agent — produces a directional signal from indicators."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, Direction, Signal, clamp_conviction, parse_direction
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
        "You are a technical analyst. Given a symbol's multi-timeframe price "
        "action and indicators (1m/3m/5m/15m/1h/daily/yearly bars with "
        "SMA/EMA stack, RSI, MACD, Bollinger bands, ATR, volume, and returns), "
        "produce a single directional read with a calibrated conviction in [0,1]. "
        "Weigh higher timeframes for trend and lower timeframes for entry timing. "
        "Be honest: most setups are neutral. Reserve high conviction (>0.7) for "
        "genuinely clean, confluent setups across timeframes. Identify nearby "
        "support/resistance and a sensible stop based on ATR. Do not invent data "
        "that is not present."
    )

    def analyze(self, snap: SymbolSnapshot) -> Signal:
        if snap.error or not snap.has_technicals:
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
            f"Multi-timeframe technicals: {json.dumps(snap.technicals, default=str)}\n\n"
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
        return Signal(
            symbol=snap.symbol,
            source=self.name,
            direction=parse_direction(r.get("direction")),
            conviction=clamp_conviction(r.get("conviction")),
            rationale=r.get("rationale", "No rationale provided."),
            horizon=r.get("horizon", "swing"),
            key_levels=levels,
            tags=["technical"],
        )
