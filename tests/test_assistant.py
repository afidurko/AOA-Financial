"""Tests for Alex executive assistant prioritization."""

from __future__ import annotations

from aoa.analytics.store import AnalyticsStore
from aoa.team.alex import AlexAgent, _deterministic_brief
from aoa.team.models import PriorityLevel


def test_deterministic_must_do_on_halt():
    brief = _deterministic_brief({"halted": True, "halt_reason": "broker down"})
    assert any(i.level is PriorityLevel.MUST for i in brief.must_do)


def test_assistant_pending_approval(tmp_path, fake_llm):
    store = AnalyticsStore(tmp_path / "a.sqlite")
    store.add_approval(kind="research", title="Review edge", summary="Momentum paper")
    agent = AlexAgent(fake_llm)
    brief = agent.prioritize(analytics_store=store, market_open=True)
    assert brief.must_do or brief.should_do
    store.close()
