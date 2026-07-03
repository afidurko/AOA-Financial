"""Tests for the composable pipeline architecture."""

from __future__ import annotations

from aoa.config import Config, RiskLimits
from aoa.data.market_data import MarketDataService
from aoa.execution.executor import Executor
from aoa.journal.store import Journal
from aoa.swarm.context import CycleContext
from aoa.swarm.pipeline import Pipeline
from aoa.swarm.stages import AnalyzeStage, IntakeStage, PortfolioStage, ScanStage, default_stages
from aoa.swarm.team import AgentTeam


def _ctx(fake_broker, fake_llm, tmp_path):
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        risk=RiskLimits(max_orders_per_cycle=5),
    )
    journal = Journal(tmp_path / "j.jsonl")
    agents = AgentTeam.from_llm(fake_llm, fake_broker, risk=cfg.risk)
    return CycleContext(
        config=cfg,
        broker=fake_broker,
        llm=fake_llm,
        journal=journal,
        market=MarketDataService(fake_broker),
        agents=agents,
        executor=Executor(fake_broker, journal, dry_run=True),
    )


def test_default_pipeline_has_seven_stages():
    stages = default_stages()
    names = [s.name for s in stages]
    assert names == ["intake", "scan", "analyze", "portfolio", "materialize", "risk", "execute"]


def test_intake_stage_populates_blackboard(fake_broker, fake_llm, tmp_path):
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    assert IntakeStage().run(ctx) is True
    assert ctx.blackboard.account is not None
    assert "AAPL" in ctx.blackboard.universe
    assert ctx.blackboard.snapshots


def test_scan_stage_shortlists_candidates(fake_broker, fake_llm, tmp_path):
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    Pipeline(stages=[IntakeStage(), ScanStage()]).run(ctx)
    assert ctx.blackboard.candidates


def test_custom_pipeline_can_swap_portfolio_stage(fake_broker, fake_llm, tmp_path):
    custom = Pipeline(
        stages=default_stages()[:3] + [PortfolioStage()] + default_stages()[4:]
    )
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    custom.run(ctx)
    assert ctx.blackboard.proposals
    assert ctx.execution is not None


def test_pipeline_journals_stage_events(fake_broker, fake_llm, tmp_path):
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    Pipeline(stages=[IntakeStage(), ScanStage()]).run(ctx)
    events = {e["event"] for e in ctx.journal.tail(20)}
    assert "pipeline.stage.start" in events
    assert "pipeline.stage.complete" in events
