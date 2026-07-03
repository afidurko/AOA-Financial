"""Risk management debate team — three risk perspectives (TradingAgents)."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, TradeProposal
from aoa.brokerage.models import Account, Position
from aoa.llm.client import LLMError
from aoa.swarm.trading_protocol import RiskDebate

_SCHEMA = {
    "type": "object",
    "properties": {
        "perspectives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "stance": {
                        "type": "string",
                        "enum": ["risk_seeking", "neutral", "risk_conservative"],
                    },
                    "assessment": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
                "required": ["stance", "assessment", "recommendation"],
                "additionalProperties": False,
            },
        },
        "facilitator_summary": {"type": "string"},
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
    },
    "required": ["perspectives", "facilitator_summary", "vetoes"],
    "additionalProperties": False,
}


class RiskDebateTeamAgent(Agent):
    name = "risk_debate"
    system_prompt = (
        "You are the risk management debate facilitator for a trading firm. Three "
        "perspectives — risk-seeking, neutral, and risk-conservative — deliberate on "
        "approved trade proposals. You may ONLY veto or tighten trades, never add risk. "
        "Return structured perspectives, a facilitator_summary, and any vetoes."
    )

    def deliberate(
        self,
        proposals: list[TradeProposal],
        account: Account,
        positions: list[Position],
    ) -> RiskDebate:
        approved = [p for p in proposals if p.approved]
        if not approved:
            return RiskDebate(
                facilitator_summary="No approved proposals to debate.",
                vetoes=[],
            )
        prompt = (
            f"Account: equity={account.equity}, settled_cash={account.settled_cash}\n"
            f"Positions: {json.dumps([_pos(p) for p in positions], default=str)}\n"
            f"Approved proposals: {json.dumps([p.to_context() for p in approved], default=str)}\n"
            "Return the risk debate as JSON."
        )
        try:
            r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        except LLMError:
            return RiskDebate(
                perspectives=[],
                facilitator_summary="Risk debate unavailable; no additional vetoes.",
                vetoes=[],
            )
        return RiskDebate(
            perspectives=list(r.get("perspectives") or []),
            facilitator_summary=str(r.get("facilitator_summary", "")),
            vetoes=list(r.get("vetoes") or []),
        )

    def apply_vetoes(self, proposals: list[TradeProposal], debate: RiskDebate) -> None:
        veto_map = {v["symbol"]: v["reason"] for v in debate.vetoes if v.get("symbol")}
        for prop in proposals:
            if not prop.approved or prop.symbol not in veto_map:
                continue
            prop.approved = False
            prop.risk_notes.append(f"Risk debate veto: {veto_map[prop.symbol]}")


def _pos(p: Position) -> dict:
    return {
        "symbol": p.symbol,
        "qty": p.qty,
        "market_value": p.market_value,
        "unrealized_pl": p.unrealized_pl,
    }
