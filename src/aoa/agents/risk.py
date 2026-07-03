"""Risk manager agent.

The binding constraints live in :mod:`aoa.risk.guards` (deterministic). This
agent runs those guards first, then optionally asks Claude for a holistic
"second opinion" that may *veto* (never approve) trades the math allowed — e.g.
over-concentration in correlated names or doubling down into a losing thesis.
The LLM can only tighten, never loosen, the deterministic decision.
"""

from __future__ import annotations

import json

from aoa.agents.base import Agent, TradeProposal
from aoa.brokerage.models import Account, Position
from aoa.config import RiskLimits
from aoa.llm.client import LLMClient, LLMError
from aoa.risk.guards import RiskGuards

_SCHEMA = {
    "type": "object",
    "properties": {
        "vetoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["symbol", "reason"],
                "additionalProperties": False,
            },
        },
        "assessment": {"type": "string"},
    },
    "required": ["vetoes", "assessment"],
    "additionalProperties": False,
}


class RiskManagerAgent(Agent):
    name = "risk_manager"
    system_prompt = (
        "You are the risk manager for an autonomous cash-account trading swarm. "
        "Deterministic guardrails have ALREADY enforced position caps, cash buffers, "
        "no-shorting, and the daily-loss kill switch. Your job is the holistic "
        "second look the math can't do: correlation/concentration across the "
        "proposed trades and existing book, sizing into elevated event risk, and "
        "adding risk into a deteriorating thesis. You may ONLY veto trades, never "
        "add or enlarge them. Veto sparingly and with a concrete reason. If the set "
        "looks prudent, return an empty veto list."
    )

    def __init__(self, llm: LLMClient, limits: RiskLimits, *, use_llm_veto: bool = True) -> None:
        super().__init__(llm)
        self.guards = RiskGuards(limits)
        self.use_llm_veto = use_llm_veto

    def review(
        self,
        proposals: list[TradeProposal],
        account: Account,
        positions: list[Position],
        *,
        starting_equity: float,
        plasticity_context: str = "",
    ) -> list[TradeProposal]:
        # 1) Deterministic guards (binding).
        self.guards.evaluate_cycle(
            proposals, account, positions, starting_equity=starting_equity
        )

        if not self.use_llm_veto:
            return proposals

        approved = [p for p in proposals if p.approved]
        if not approved:
            return proposals

        # 2) LLM holistic veto over the approved set.
        try:
            prompt = (
                f"Account: equity={account.equity}, settled_cash={account.settled_cash}\n"
                f"Existing positions: "
                f"{json.dumps([_pos_ctx(p) for p in positions], default=str)}\n"
                f"Approved proposals: "
                f"{json.dumps([p.to_context() for p in approved], default=str)}\n"
            )
            if plasticity_context:
                prompt += f"Cross-cycle memory:\n{plasticity_context}\n"
            prompt += "\nReturn any vetoes as JSON."
            r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        except LLMError:
            # Fail safe: if the second opinion is unavailable, keep deterministic result.
            return proposals

        veto_symbols = {v["symbol"]: v["reason"] for v in r.get("vetoes", [])}
        for prop in approved:
            if prop.symbol in veto_symbols:
                prop.approved = False
                prop.risk_notes.append(f"LLM veto: {veto_symbols[prop.symbol]}")
        return proposals


def _pos_ctx(p: Position) -> dict:
    return {
        "symbol": p.symbol,
        "asset_class": p.asset_class.value,
        "qty": p.qty,
        "market_value": p.market_value,
        "unrealized_pl": p.unrealized_pl,
    }
