"""Tests for TradingAgents-inspired multi-agent trading flow."""

from __future__ import annotations

from aoa.agents.research import ResearchTeamAgent
from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.swarm.orchestrator import Orchestrator
from aoa.swarm.stages import default_stages
from aoa.swarm.trading_protocol import AnalystReport


def _config(**kwargs):
    defaults = dict(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=True,
        trading_agents_enabled=True,
        trading_agents_debate_rounds=1,
        risk=RiskLimits(max_orders_per_cycle=5),
    )
    defaults.update(kwargs)
    return Config(**defaults)


def test_pipeline_includes_trading_agents_stages():
    names = [s.name for s in default_stages()]
    assert "risk_debate" in names
    assert "fund_manager" in names


def test_trading_agents_full_cycle_journals_debate(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    orch = Orchestrator(_config(), fake_broker, fake_llm, journal)
    orch.run_cycle()
    events = {e["event"] for e in journal.tail(80)}
    assert "analyst.report" in events
    assert "research.debate" in events
    assert "risk.debate" in events
    assert "fund_manager.review" in events


def test_trading_agents_analyze_populates_four_reports(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    orch = Orchestrator(_config(), fake_broker, fake_llm, journal)
    result = orch.run_cycle()
    env = result.blackboard.environment
    assert "analyst_reports:AAPL" in env.domains
    reports = env.domains["analyst_reports:AAPL"].effective()["reports"]
    analysts = {r["analyst"] for r in reports}
    assert analysts == {"technical", "fundamental", "news", "sentiment"}
    assert "research:AAPL" in env.domains


def test_legacy_mode_skips_trading_agents_stages(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    orch = Orchestrator(
        _config(trading_agents_enabled=False), fake_broker, fake_llm, journal
    )
    orch.run_cycle()
    events = {e["event"] for e in journal.tail(80)}
    assert "research.debate" not in events
    assert "risk.debate" not in events
    assert "fund_manager.review" not in events


def test_research_debate_produces_prevailing_view(fake_llm):
    agent = ResearchTeamAgent(fake_llm)
    reports = [
        AnalystReport("AAPL", "technical", "bullish", 0.8, "uptrend"),
        AnalystReport("AAPL", "fundamental", "bullish", 0.6, "stable"),
    ]
    debate = agent.debate("AAPL", reports, rounds=1)
    assert debate.prevailing_view in {"bullish", "bearish", "neutral"}
    assert debate.bull_argument
    assert debate.bear_argument
