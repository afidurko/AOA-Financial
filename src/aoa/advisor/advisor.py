"""The certified financial assistant.

A fiduciary, CFP-style advisor that answers questions conversationally and can
produce a full written financial plan. It is *agentic*: every numerical claim is
grounded by calling a deterministic tool (see :mod:`aoa.advisor.tools`) rather
than doing arithmetic in the model's head.

This is the advice-and-planning counterpart to the trading swarm. It does not
place orders; it reasons about your whole financial picture and tells you what it
would do and why.
"""

from __future__ import annotations

from aoa.advisor.profile import FinancialProfile
from aoa.advisor.tools import build_registry
from aoa.brokerage.base import Broker
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient

DISCLAIMER = (
    "This is an automated, educational financial-planning assistant — not a "
    "licensed human advisor, and not individualized investment, tax, or legal "
    "advice. Verify anything important with a qualified professional before acting."
)

SYSTEM_PROMPT = (
    "You are a certified-financial-planner-style assistant acting under a "
    "FIDUCIARY standard: the user's best interest comes before all else. You give "
    "holistic personal-finance guidance — cash flow and budgeting, emergency "
    "funds, debt paydown, retirement, asset allocation, and tax-advantaged "
    "accounts.\n\n"
    "HARD RULES:\n"
    "1. Never state a number you have not obtained from a tool. For every figure "
    "(net worth, savings rate, months of runway, payoff time, projections, "
    "contribution room, allocation drift) you MUST call the relevant tool and use "
    "its output. Do not estimate arithmetic yourself.\n"
    "2. Start by calling get_financial_profile to ground yourself in the user's "
    "actual situation before giving advice.\n"
    "3. If key information is missing (flagged in 'missing_information'), say so "
    "and ask for it rather than guessing.\n"
    "4. Follow a sensible priority order when relevant: (a) cover essential "
    "expenses and a starter emergency fund, (b) capture any employer 401(k) "
    "match, (c) pay down high-interest debt, (d) build a full emergency fund, "
    "(e) tax-advantaged retirement saving, (f) other goals.\n"
    "5. Be concrete and specific: give dollar amounts, timeframes, and the single "
    "next action. Explain the 'why'. Acknowledge tradeoffs and uncertainty.\n"
    "6. You are an educational tool, not a licensed professional. Do not give "
    "specific tax-filing, legal, or insurance-product advice; point to a "
    "professional for those. Never promise returns.\n\n"
    "Write plainly and warmly, like a trusted advisor sitting across the table. "
    "Prefer short paragraphs and tight bullet lists over walls of text."
)

PLAN_REQUEST = (
    "Produce a complete financial plan for me. Use your tools to ground every "
    "number, then cover, in this order, each as a short section with a header:\n"
    "1. Snapshot — net worth and cash-flow/savings rate.\n"
    "2. Emergency fund — coverage vs. target and the gap.\n"
    "3. Debt — payoff plan (compare avalanche vs snowball) and what I should do.\n"
    "4. Retirement — projection vs. target, and whether I'm on track.\n"
    "5. Asset allocation — current vs. age-appropriate target and any rebalancing.\n"
    "6. Tax-advantaged accounts — remaining 401(k)/IRA/HSA room to use this year.\n"
    "7. Action plan — the 3–5 highest-impact moves, in priority order.\n"
    "End with one sentence on the most important thing to do this month."
)


class FinancialAdvisor:
    """An agentic, fiduciary financial assistant over a :class:`FinancialProfile`."""

    def __init__(
        self,
        llm: LLMClient,
        profile: FinancialProfile,
        broker: Broker | None = None,
        journal: Journal | None = None,
        *,
        max_iterations: int = 10,
    ) -> None:
        self.llm = llm
        self.profile = profile
        self.registry = build_registry(profile, broker)
        self.journal = journal
        self.max_iterations = max_iterations

    # ------------------------------------------------------------------ public
    def chat(self, message: str, history: list[dict] | None = None) -> dict:
        """Answer one user message, grounding all math in tools.

        Returns ``{"reply", "messages", "tools_used"}``. Pass the returned
        ``messages`` back as ``history`` to continue the conversation.
        """
        messages = list(history or [])
        messages.append({"role": "user", "content": message})
        return self._respond(messages, kind="chat", request=message)

    def plan(self) -> dict:
        """Generate a full written financial plan."""
        messages = [{"role": "user", "content": PLAN_REQUEST}]
        return self._respond(messages, kind="plan", request=PLAN_REQUEST)

    # ----------------------------------------------------------------- internal
    def _respond(self, messages: list[dict], *, kind: str, request: str) -> dict:
        result = self.llm.run_tools(
            SYSTEM_PROMPT,
            messages,
            self.registry.specs(),
            self.registry.run,
            max_iterations=self.max_iterations,
        )
        if self.journal is not None:
            self.journal.record(
                f"advisor.{kind}",
                {
                    "request": request[:500],
                    "tools_used": [c["name"] for c in result.tool_calls],
                    "stopped_at_limit": result.stopped_at_limit,
                    "reply_preview": result.text[:500],
                },
            )
        return {
            "reply": result.text,
            "messages": result.messages,
            "tools_used": [c["name"] for c in result.tool_calls],
            "stopped_at_limit": result.stopped_at_limit,
        }
