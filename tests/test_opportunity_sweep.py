"""Tests for idle opportunity sweep loop."""

from __future__ import annotations

import threading
import time

from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.notify.policy import NotificationPolicy
from aoa.notify.types import NotificationKind
from aoa.team.models import CatalystReport, DecisionBrief, TrendDirection, TrendReport
from aoa.team.orchestrator import TeamCycleResult, TeamOrchestrator
from aoa.web.loop_runner import LoopRunner
from aoa.web.opportunity_sweep import OpportunitySweepLoop, SweepActivityTracker


def _config(**kwargs):
    base = dict(
        broker="moomoo",
        anthropic_api_key="x",
        universe=("AAPL",),
        dry_run=True,
        opportunity_sweep_enabled=True,
        opportunity_sweep_seconds=900,
        opportunity_sweep_poll_seconds=1,
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )
    base.update(kwargs)
    return Config(**base)


def test_tracker_resets_on_alert_activity():
    tracker = SweepActivityTracker(threshold_seconds=60)
    policy = NotificationPolicy()
    result = TeamCycleResult(halted=True, halt_reason="broker down")
    tracker.record_cycle_result(result, policy)
    assert tracker.seconds_idle() < 1.0


def test_tracker_stays_idle_without_opportunity_notifications():
    tracker = SweepActivityTracker(threshold_seconds=1)
    policy = NotificationPolicy(min_conviction=0.99, push_opportunities=True)
    result = TeamCycleResult(
        trends=[
            TrendReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                strength=0.5,
                timeframe="daily",
                rationale="weak trend only",
            )
        ]
    )
    tracker.record_cycle_result(result, policy)
    time.sleep(1.1)
    assert tracker.is_idle()


def test_evaluate_sweep_surfaces_high_conviction_setups():
    policy = NotificationPolicy(min_conviction=0.6, push_opportunities=True)
    trends = [
        TrendReport(
            symbol="AAPL",
            direction=TrendDirection.UP,
            strength=0.75,
            timeframe="swing",
            rationale="Volume breakout with higher lows.",
        )
    ]
    decision = DecisionBrief(
        recommendations=[{"symbol": "MSFT", "confidence": 0.7, "rationale": "Alan likes MSFT"}],
        summary="Two names stand out.",
        confidence=0.7,
    )
    catalysts = [
        CatalystReport(
            symbol="AAPL",
            catalyst_summary="Earnings beat expectations.",
            event_risk="medium",
            headline_sentiment="bullish",
            impact_score=0.8,
        )
    ]
    notes = policy.evaluate_sweep(trends, decision, catalysts=catalysts)
    kinds = {n.kind for n in notes}
    assert NotificationKind.OPPORTUNITY in kinds
    assert NotificationKind.ANALYSIS in kinds
    assert any(n.symbol == "AAPL" for n in notes)
    assert any(n.symbol == "MSFT" for n in notes)


def test_run_opportunity_sweep_journals_events(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "sweep.jsonl")
    team = TeamOrchestrator(_config(), fake_broker, fake_llm, journal)
    result = team.run_opportunity_sweep()
    assert result.trends
    assert result.decision is not None
    events = {e["event"] for e in journal.tail(50)}
    assert "team.sweep.triggered" in events
    assert "team.sweep.complete" in events
    assert "team.tom.trends" in events
    assert "team.hailey.catalysts" in events


def test_sweep_loop_fires_after_idle(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "loop.jsonl")
    cfg = _config(opportunity_sweep_seconds=1, opportunity_sweep_poll_seconds=1)
    team = TeamOrchestrator(cfg, fake_broker, fake_llm, journal)
    cycle_lock = threading.Lock()
    sweep = OpportunitySweepLoop(
        team,
        enabled=True,
        threshold_seconds=1,
        poll_seconds=1,
        cycle_lock=cycle_lock,
    )
    sweep.start()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if sweep.state.sweeps_completed >= 1:
            break
        time.sleep(0.2)
    sweep.stop()
    assert sweep.state.sweeps_completed >= 1
    events = {e["event"] for e in journal.tail(80)}
    assert "team.sweep.triggered" in events


def test_loop_runner_records_cycle_and_exposes_sweep_state(fake_broker, fake_llm):
    team = TeamOrchestrator(_config(), fake_broker, fake_llm)
    runner = LoopRunner(team, cycle_seconds=900)
    result = runner.run_once()
    assert result.halted is False
    state = runner.sweep_state()
    assert state.enabled is True
    assert state.threshold_seconds == 900
    assert state.last_activity_at is not None
    assert state.idle_seconds < 5
