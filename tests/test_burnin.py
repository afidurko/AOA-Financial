"""Tests for paper burn-in and TradingAgents reporting."""

from __future__ import annotations

from aoa.agents.base import Direction
from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.reporting import summarize_journal
from aoa.swarm.environment import MeshedView, SwarmEnvironment
from aoa.swarm.orchestrator import Orchestrator


def test_summarize_journal_counts_trading_agents_events():
    entries = [
        {"event": "cycle.start", "ts": "2025-01-01T00:00:00Z"},
        {"event": "research.debate", "symbol": "AAPL"},
        {"event": "risk.debate", "facilitator_summary": "ok"},
        {"event": "fund_manager.review", "approved": 1},
    ]
    s = summarize_journal(entries)
    assert s.cycles == 1
    assert s.research_debates == 1
    assert s.risk_debates == 1
    assert s.fund_manager_reviews == 1


def test_per_symbol_context_includes_analyst_reports():
    env = SwarmEnvironment()
    env.set_meshed(
        MeshedView(
            symbol="AAPL",
            direction=Direction.BULLISH,
            conviction=0.7,
            rationale="aligned",
        )
    )
    env.set_domain(
        "analyst_reports:AAPL",
        {
            "reports": [
                {"analyst": "news", "direction": "bullish", "conviction": 0.6},
            ]
        },
    )
    env.set_domain(
        "research:AAPL",
        {"prevailing_view": "bullish", "conviction": 0.65},
    )
    row = env.per_symbol_context()[0]
    assert row["analyst_reports"]
    assert row["research_debate"]["prevailing_view"] == "bullish"


def test_portfolio_receives_trading_agents_context(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=True,
        trading_agents_enabled=True,
        risk=RiskLimits(max_orders_per_cycle=5),
    )
    orch = Orchestrator(cfg, fake_broker, fake_llm, journal)
    result = orch.run_cycle()
    ctx = result.blackboard.environment.per_symbol_context()
    assert ctx
    assert "analyst_reports" in ctx[0] or "research_debate" in ctx[0]
