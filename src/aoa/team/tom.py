"""Tom — trend analyst on the agent team."""

from __future__ import annotations

import json

from aoa.agents.base import Agent
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import TrendDirection, TrendReport

_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["up", "down", "sideways", "unclear"]},
        "strength": {"type": "number"},
        "timeframe": {"type": "string", "enum": ["intraday", "swing", "position"]},
        "rationale": {"type": "string"},
        "key_observations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["direction", "strength", "timeframe", "rationale", "key_observations"],
    "additionalProperties": False,
}

_ROLE = (
    "You are Tom, the trend analyst on an autonomous trading team. Your job is "
    "to read price action and indicators and characterize the prevailing trend "
    "(up, down, sideways, or unclear) with a calibrated strength in [0,1]. Focus "
    "on trend structure: higher highs/lows, moving-average alignment, momentum "
    "persistence, and volume confirmation. Be conservative — most names are not "
    "in clean trends. Do not invent data that is not present."
)

KNOWLEDGE = (
    "Finance reference library (https://github.com/shashankvemuri/Finance) — "
    "150+ quantitative finance Python programs for gathering, manipulating, and "
    "analyzing stock market data. Setup:\n"
    "git clone https://github.com/shashankvemuri/Finance.git\n"
    "cd Finance\n"
    "pip install -r requirements.txt"
)


class TomAgent(Agent):
    name = "tom"
    display_name = "Tom"
    role = "Trend Analyst"

    knowledge = KNOWLEDGE
    system_prompt = _ROLE + "\n\nReference knowledge:\n" + KNOWLEDGE

    def analyze_trends(self, snapshots: dict[str, SymbolSnapshot]) -> list[TrendReport]:
        reports: list[TrendReport] = []
        for _symbol, snap in snapshots.items():
            reports.append(self.analyze_symbol(snap))
        return reports

    def analyze_symbol(self, snap: SymbolSnapshot) -> TrendReport:
        if snap.error or not snap.technicals:
            return TrendReport(
                symbol=snap.symbol,
                direction=TrendDirection.UNCLEAR,
                strength=0.0,
                timeframe="swing",
                rationale=f"No usable data ({snap.error or 'empty'}).",
            )
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Quote: {json.dumps(snap.to_context()['quote'])}\n"
            f"Technicals: {json.dumps(snap.technicals, default=str)}\n\n"
            "Characterize the trend. Return JSON."
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        return TrendReport(
            symbol=snap.symbol,
            direction=TrendDirection(r["direction"]),
            strength=_clamp(r["strength"]),
            timeframe=r.get("timeframe", "swing"),
            rationale=r["rationale"],
            key_observations=list(r.get("key_observations") or []),
        )


def _clamp(v: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
