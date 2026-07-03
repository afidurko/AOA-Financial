"""Fund manager — final approval gate (TradingAgents)."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, TradeProposal
from aoa.brokerage.models import Account
from aoa.llm.client import LLMError

_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
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
        "commentary": {"type": "string"},
    },
    "required": ["approved", "vetoes", "commentary"],
    "additionalProperties": False,
}


class FundManagerAgent(Agent):
    name = "fund_manager"
    system_prompt = (
        "You are the fund manager with final approval authority before orders execute. "
        "Review trader proposals and risk-team deliberation. You may ONLY veto or "
        "tighten — never add or enlarge trades. If the book looks prudent, approve."
    )

    def review(
        self,
        proposals: list[TradeProposal],
        account: Account,
        *,
        risk_debate_summary: str = "",
        portfolio_commentary: str = "",
    ) -> dict:
        approved_props = [p for p in proposals if p.approved]
        if not approved_props:
            return {"approved": True, "vetoes": [], "commentary": "No approved trades to review."}

        prompt = (
            f"Account: equity={account.equity}, settled_cash={account.settled_cash}\n"
            f"Portfolio commentary: {portfolio_commentary}\n"
            f"Risk debate summary: {risk_debate_summary}\n"
            f"Approved proposals: "
            f"{json.dumps([p.to_context() for p in approved_props], default=str)}\n"
            "Return fund manager decision as JSON."
        )
        try:
            return self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        except LLMError:
            return {
                "approved": True,
                "vetoes": [],
                "commentary": "Fund manager unavailable; keeping prior approvals.",
            }

    def apply_decision(self, proposals: list[TradeProposal], decision: dict) -> None:
        if decision.get("approved") is False:
            for prop in proposals:
                if prop.approved:
                    prop.approved = False
                    prop.risk_notes.append("Fund manager rejected the book.")
            return
        veto_map = {v["symbol"]: v["reason"] for v in decision.get("vetoes", []) if v.get("symbol")}
        for prop in proposals:
            if not prop.approved or prop.symbol not in veto_map:
                continue
            prop.approved = False
            prop.risk_notes.append(f"Fund manager veto: {veto_map[prop.symbol]}")
