"""Tests for the composable pipeline architecture."""

from __future__ import annotations

from aoa.config import Config, RiskLimits
from aoa.data.market_data import MarketDataService
from aoa.data.news import NullNewsFeed
from aoa.execution.executor import Executor
from aoa.journal.store import Journal
from aoa.state import StateStore
from aoa.swarm.context import CycleContext
from aoa.swarm.pipeline import Pipeline
from aoa.swarm.stages import AnalyzeStage, IntakeStage, ScanStage, default_stages
from aoa.swarm.team import AgentTeam


def _ctx(fake_broker, fake_llm, tmp_path, *, parallel_workers=1):
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        parallel_workers=parallel_workers,
        risk=RiskLimits(max_orders_per_cycle=5),
    )
    journal = Journal(tmp_path / "j.jsonl")
    state = StateStore(tmp_path / "state.json")
    agents = AgentTeam.from_llm(fake_llm, fake_broker, risk=cfg.risk)
    return CycleContext(
        config=cfg,
        broker=fake_broker,
        llm=fake_llm,
        journal=journal,
        market=MarketDataService(fake_broker),
        agents=agents,
        executor=Executor(fake_broker, journal, dry_run=True, state=state),
        news=NullNewsFeed(),
        state=state,
    )


def test_default_pipeline_has_eight_stages():
    stages = default_stages()
    names = [s.name for s in stages]
    assert names == [
        "intake",
        "scan",
        "analyze",
        "portfolio",
        "materialize",
        "risk",
        "execute",
        "plasticity",
    ]


def test_intake_stage_populates_blackboard(fake_broker, fake_llm, tmp_path):
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    assert IntakeStage().run(ctx) is True
    assert ctx.blackboard.account is not None
    assert "AAPL" in ctx.blackboard.universe
    assert ctx.blackboard.snapshots


def test_scan_stage_creates_checkpoint(fake_broker, fake_llm, tmp_path):
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    Pipeline(stages=[IntakeStage(), ScanStage()]).run(ctx)
    assert ctx.blackboard.candidates
    assert "scan" in ctx.blackboard.environment.checkpoints


def test_analyze_stage_parallel_matches_sequential(fake_broker, fake_llm, tmp_path):
    seq_ctx = _ctx(fake_broker, fake_llm, tmp_path, parallel_workers=1)
    IntakeStage().run(seq_ctx)
    ScanStage().run(seq_ctx)
    AnalyzeStage().run(seq_ctx)

    par_ctx = _ctx(fake_broker, fake_llm, tmp_path, parallel_workers=4)
    IntakeStage().run(par_ctx)
    ScanStage().run(par_ctx)
    AnalyzeStage().run(par_ctx)

    seq_view = seq_ctx.blackboard.environment.meshed_views["AAPL"]
    par_view = par_ctx.blackboard.environment.meshed_views["AAPL"]
    assert seq_view.direction == par_view.direction
    assert seq_view.conviction == par_view.conviction


def test_pipeline_emits_stage_events(fake_broker, fake_llm, tmp_path):
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    Pipeline(stages=[IntakeStage(), ScanStage()]).run(ctx)
    kinds = [e.kind for e in ctx.blackboard.events.events]
    assert "stage.start" in kinds
    assert "stage.complete" in kinds
    assert "stage.checkpoint" in kinds


def test_pipeline_run_until_journals_stages(fake_broker, fake_llm, tmp_path):
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    Pipeline(stages=[IntakeStage(), ScanStage()]).run_until(ctx, "analyze")
    kinds = [r["event"] for r in ctx.journal.tail(20)]
    assert "pipeline.stage.start" in kinds
    assert "pipeline.stage.complete" in kinds


def test_environment_checkpoints_after_marked_stages(fake_broker, fake_llm, tmp_path):
    ctx = _ctx(fake_broker, fake_llm, tmp_path)
    Pipeline(stages=default_stages()[:3]).run(ctx)  # intake, scan, analyze
    checkpoints = ctx.blackboard.environment.list_checkpoints()
    assert "scan" in checkpoints
    assert "analyze" in checkpoints
