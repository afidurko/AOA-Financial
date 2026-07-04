"""Morgan — market context, volume, and liquidity analyst."""

from __future__ import annotations

import json

from aoa.agents.base import Agent
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import MarketContextReport

_SCHEMA = {
    "type": "object",
    "properties": {
        "volume_regime": {"type": "string", "enum": ["elevated", "normal", "thin"]},
        "volume_ratio": {"type": "number"},
        "liquidity_note": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["volume_regime", "volume_ratio", "liquidity_note", "summary"],
    "additionalProperties": False,
}


class MorganAgent(Agent):
    name = "morgan"
    display_name = "Morgan"
    role = "Market & Volume Analyst"

    system_prompt = (
        "You are Morgan, the market and volume analyst on an autonomous trading team. "
        "Given OHLCV technical snapshots, characterize volume regime (elevated, normal, "
        "thin), relative volume vs the 20-day average, and liquidity implications for "
        "cash-account trading. Be concise and factual — cite only metrics present in "
        "the input. Flag unusual volume that may confirm or contradict trend setups."
    )

    def analyze_contexts(self, snapshots: dict[str, SymbolSnapshot]) -> list[MarketContextReport]:
        return [self.analyze_symbol(snap) for snap in snapshots.values()]

    def analyze_symbol(self, snap: SymbolSnapshot) -> MarketContextReport:
        baseline = _volume_baseline(snap)
        if snap.error or not snap.has_technicals:
            return MarketContextReport(
                symbol=snap.symbol,
                volume_regime="thin",
                volume_ratio=baseline.get("volume_ratio"),
                liquidity_note="Insufficient market data.",
                summary=f"{snap.symbol}: data unavailable.",
            )

        prompt = (
            f"Symbol snapshot:\n{json.dumps(snap.to_context(), default=str)}\n"
            f"Computed volume hints:\n{json.dumps(baseline, default=str)}\n"
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        ratio = r.get("volume_ratio")
        if ratio is None:
            ratio = baseline.get("volume_ratio")
        return MarketContextReport(
            symbol=snap.symbol,
            volume_regime=str(r.get("volume_regime", baseline.get("regime", "normal"))),
            volume_ratio=float(ratio) if ratio is not None else None,
            liquidity_note=str(r.get("liquidity_note", "")),
            summary=str(r.get("summary", "")),
        )


def _volume_baseline(snap: SymbolSnapshot) -> dict:
    daily = snap.technicals.get("1Day") or snap.technicals.get("1day") or {}
    vm = daily.get("volume_metrics") or {}
    ratio = vm.get("volume_ratio")
    regime = "normal"
    if ratio is not None:
        if ratio >= 1.5:
            regime = "elevated"
        elif ratio < 0.7:
            regime = "thin"
    return {
        "volume_ratio": ratio,
        "latest_volume": vm.get("latest_volume"),
        "avg_volume_20d": vm.get("avg_volume_20d"),
        "regime": regime,
    }
