"""Research team — bull/bear debate with facilitator (TradingAgents)."""

from __future__ import annotations

import json

from aoa.agents.base import Agent, clamp_conviction
from aoa.llm.client import LLMError
from aoa.swarm.trading_protocol import AnalystReport, ResearchDebate

_BULL_SCHEMA = {
    "type": "object",
    "properties": {
        "argument": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "conviction": {"type": "number"},
    },
    "required": ["argument", "key_points", "conviction"],
    "additionalProperties": False,
}

_BEAR_SCHEMA = {
    "type": "object",
    "properties": {
        "argument": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "conviction": {"type": "number"},
    },
    "required": ["argument", "key_points", "conviction"],
    "additionalProperties": False,
}

_FACILITATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "prevailing_view": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "conviction": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["prevailing_view", "conviction", "rationale"],
    "additionalProperties": False,
}


class ResearchTeamAgent(Agent):
    name = "research"
    system_prompt = (
        "You are part of a trading firm's research team. Bull and bear researchers "
        "debate analyst reports; a facilitator selects the prevailing view. Be balanced "
        "and evidence-based — cite analyst reports, do not invent data."
    )

    def debate(
        self,
        symbol: str,
        reports: list[AnalystReport],
        *,
        rounds: int = 1,
    ) -> ResearchDebate:
        reports_ctx = [r.to_context() for r in reports]
        base_prompt = (
            f"Symbol: {symbol}\n"
            f"Analyst reports:\n{json.dumps(reports_ctx, default=str)}\n"
        )

        bull = self._bull_case(base_prompt)
        bear = self._bear_case(base_prompt, bull_argument=bull.get("argument", ""))

        debate_rounds: list[dict[str, str]] = []
        for i in range(max(1, rounds)):
            debate_rounds.append(
                {
                    "round": str(i + 1),
                    "bull": bull.get("argument", ""),
                    "bear": bear.get("argument", ""),
                }
            )

        verdict = self._facilitate(symbol, bull, bear, reports_ctx)
        return ResearchDebate(
            symbol=symbol,
            bull_argument=bull.get("argument", ""),
            bear_argument=bear.get("argument", ""),
            rounds=debate_rounds,
            prevailing_view=verdict.get("prevailing_view", "neutral"),
            conviction=clamp_conviction(verdict.get("conviction")),
            rationale=verdict.get("rationale", ""),
        )

    def _bull_case(self, prompt: str) -> dict:
        try:
            return self.llm.structured(
                self.system_prompt + " You are the BULLISH researcher.",
                prompt + "\nMake the bullish investment case as JSON.",
                _BULL_SCHEMA,
            )
        except LLMError:
            return {"argument": "Bull case unavailable.", "key_points": [], "conviction": 0.0}

    def _bear_case(self, prompt: str, *, bull_argument: str) -> dict:
        try:
            return self.llm.structured(
                self.system_prompt + " You are the BEARISH researcher.",
                prompt + f"\nBull case to counter:\n{bull_argument}\n"
                "Make the bearish risk case as JSON.",
                _BEAR_SCHEMA,
            )
        except LLMError:
            return {"argument": "Bear case unavailable.", "key_points": [], "conviction": 0.0}

    def _facilitate(self, symbol: str, bull: dict, bear: dict, reports: list) -> dict:
        prompt = (
            f"Symbol: {symbol}\n"
            f"Analyst reports: {json.dumps(reports, default=str)}\n"
            f"Bull: {bull.get('argument', '')}\n"
            f"Bear: {bear.get('argument', '')}\n"
            "Select the prevailing view as JSON."
        )
        try:
            return self.llm.structured(
                self.system_prompt + " You are the debate FACILITATOR.",
                prompt,
                _FACILITATOR_SCHEMA,
            )
        except LLMError:
            bull_c = float(bull.get("conviction", 0) or 0)
            bear_c = float(bear.get("conviction", 0) or 0)
            if bull_c > bear_c + 0.1:
                view = "bullish"
            elif bear_c > bull_c + 0.1:
                view = "bearish"
            else:
                view = "neutral"
            return {
                "prevailing_view": view,
                "conviction": clamp_conviction(abs(bull_c - bear_c)),
                "rationale": "Facilitator fallback from conviction spread.",
            }
