"""Portfolio manager agent — turns signals into concrete trade proposals.

It sees the full picture: per-symbol technical & fundamental signals, any options
ideas, current positions, and the account. It outputs target trades expressed as
*dollar notionals*; the orchestrator converts those to share/contract quantities
and the risk manager vets them against hard limits.
"""

from __future__ import annotations

import json

from aoa.agents.base import Agent
from aoa.llm.client import LLMError

_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "instrument": {"type": "string", "enum": ["equity", "option"]},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "target_notional": {"type": "number"},
                    "strategy": {"type": "string"},
                    "conviction": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": [
                    "symbol",
                    "instrument",
                    "side",
                    "target_notional",
                    "strategy",
                    "conviction",
                    "rationale",
                ],
                "additionalProperties": False,
            },
        },
        "portfolio_commentary": {"type": "string"},
    },
    "required": ["proposals", "portfolio_commentary"],
    "additionalProperties": False,
}


class PortfolioManagerAgent(Agent):
    name = "portfolio_manager"
    system_prompt = (
        "You are the portfolio manager for an autonomous CASH-account trading swarm. "
        "You receive, per symbol, a meshed view (unified synthesis of technical "
        "and fundamental signals) plus per-domain context, any options idea, "
        "current positions, and the account snapshot. "
        "Decide a focused set of trades that best expresses the highest-conviction, "
        "best-corroborated views while respecting diversification and the cash on "
        "hand. Rules you must honor:\n"
        "- This is a CASH account: only buy what settled cash can cover; no shorting "
        "equities; options limited to long calls/puts, covered calls, cash-secured "
        "puts.\n"
        "- Express each trade as a target DOLLAR notional (target_notional). For an "
        "option, 'symbol' must be the exact OCC option symbol from the provided "
        "options idea and instrument='option'.\n"
        "- To exit/trim an existing position, propose side='sell' on it.\n"
        "- Size by conviction and corroboration. When signals conflict or are weak, "
        "propose nothing for that name. It is correct to return an empty list on a "
        "quiet day.\n"
        "- Never exceed available settled cash in aggregate buy notional."
    )

    def decide(
        self,
        per_symbol: list[dict],
        positions: list[dict],
        account: dict,
        *,
        max_new_positions: int = 5,
    ) -> dict:
        prompt = (
            f"Account: {json.dumps(account)}\n"
            f"Current positions: {json.dumps(positions, default=str)}\n"
            f"Per-symbol analysis (meshed views + domain context):\n"
            f"{json.dumps(per_symbol, default=str)}\n\n"
            f"Propose at most {max_new_positions} new trades (plus any exits). "
            "Return JSON."
        )
        try:
            return self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        except LLMError:
            return {
                "proposals": [],
                "portfolio_commentary": "Portfolio manager unavailable (LLM error).",
            }
