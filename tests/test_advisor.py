"""End-to-end advisor test using a fake, tool-driving LLM (no network)."""

from __future__ import annotations

from aoa.advisor.advisor import FinancialAdvisor
from aoa.advisor.profile import sample_profile
from aoa.llm.client import ToolRunResult


class FakeToolLLM:
    """A stand-in for the agentic loop.

    It exercises the real tool runner — calling the requested tools in order — then
    returns a canned prose answer. This verifies the advisor wires the registry and
    the loop together without hitting Anthropic.
    """

    def __init__(self, tools_to_call):
        self.tools_to_call = tools_to_call
        self.model = "fake"

    def run_tools(self, system, messages, tools, tool_runner, *, max_iterations=10,
                  max_tokens=None):
        available = {spec["name"] for spec in tools}
        calls = []
        for name, payload in self.tools_to_call:
            assert name in available, f"advisor did not expose tool {name}"
            result = tool_runner(name, payload)
            assert "error" not in result, f"tool {name} errored: {result}"
            calls.append({"name": name, "input": payload})
        return ToolRunResult(
            text="Here is your grounded analysis.",
            messages=list(messages) + [{"role": "assistant", "content": "..."}],
            tool_calls=calls,
        )


def test_advisor_chat_runs_tools_and_returns_reply():
    prof = sample_profile()
    llm = FakeToolLLM([
        ("get_financial_profile", {}),
        ("compute_net_worth", {}),
        ("emergency_fund", {}),
    ])
    advisor = FinancialAdvisor(llm, prof)
    result = advisor.chat("How am I doing financially?")
    assert result["reply"] == "Here is your grounded analysis."
    assert result["tools_used"] == [
        "get_financial_profile", "compute_net_worth", "emergency_fund"
    ]
    assert result["stopped_at_limit"] is False


def test_advisor_plan_runs_and_journals(tmp_path):
    from aoa.journal.store import Journal

    journal = Journal(tmp_path / "j.jsonl")
    llm = FakeToolLLM([
        ("get_financial_profile", {}),
        ("compute_debt_payoff_unused", {}),
    ] if False else [("get_financial_profile", {}), ("debt_payoff", {"extra_monthly": 300})])
    advisor = FinancialAdvisor(llm, sample_profile(), journal=journal)
    result = advisor.plan()
    assert result["reply"]
    entries = journal.tail(5)
    assert any(e["event"] == "advisor.plan" for e in entries)


def test_advisor_chat_history_continues():
    prof = sample_profile()
    llm = FakeToolLLM([("get_financial_profile", {})])
    advisor = FinancialAdvisor(llm, prof)
    first = advisor.chat("hi")
    # The returned transcript can be fed back in as history.
    second = advisor.chat("and my debt?", history=first["messages"])
    assert second["reply"]
