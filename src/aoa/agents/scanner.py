"""Scanner agent — narrows a broad universe to a shortlist worth deep analysis."""

from __future__ import annotations

import json

from aoa.agents.base import Agent
from aoa.data.market_data import SymbolSnapshot
from aoa.llm.client import LLMError

_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "reason": {"type": "string"},
                    "priority": {"type": "number"},
                },
                "required": ["symbol", "reason", "priority"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


class ScannerAgent(Agent):
    name = "scanner"
    system_prompt = (
        "You are a market scanner for a cash-account trading swarm. You are given "
        "lightweight multi-timeframe technical snapshots for a universe of liquid "
        "US equities. Your job is to surface the handful of names showing the most "
        "actionable setups (momentum, mean-reversion, volatility expansion, trend "
        "with pullback, volume spikes). Compare intraday (1m–15m), hourly, daily, "
        "and yearly context when present. "
        "You do NOT decide trades — you only shortlist what deserves deeper study. "
        "Prefer liquid names with clean technicals and avoid those with missing data. "
        "Be selective: quality over quantity."
    )

    def scan(
        self, snapshots: dict[str, SymbolSnapshot], *, max_candidates: int = 6
    ) -> list[dict]:
        universe_ctx = [
            s.to_context()
            for s in snapshots.values()
            if s.error is None and s.has_technicals
        ]
        if not universe_ctx:
            return []
        prompt = (
            f"Universe technical snapshots (JSON):\n{json.dumps(universe_ctx, default=str)}\n\n"
            f"Select up to {max_candidates} candidates with the strongest setups. "
            "Assign each a priority from 0 (weak) to 1 (strong). Return JSON."
        )
        try:
            result = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        except LLMError:
            return []
        candidates = result.get("candidates", [])
        candidates.sort(key=lambda c: c.get("priority", 0), reverse=True)
        return candidates[:max_candidates]
