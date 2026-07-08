"""Tests for structured notification policy."""

from __future__ import annotations

from aoa.notify.policy import NotificationPolicy
from aoa.notify.types import NotificationKind
from aoa.team.models import TrendDirection, TrendReport
from aoa.team.orchestrator import TeamCycleResult


def test_policy_halts_and_opportunities():
    policy = NotificationPolicy(push_halts=True, min_conviction=0.5)
    result = TeamCycleResult(halted=True, halt_reason="broker down")
    notes = policy.evaluate_cycle(result, run_id="r1")
    assert any(n.kind is NotificationKind.ALERT for n in notes)


def test_policy_skips_low_conviction_trends():
    policy = NotificationPolicy(min_conviction=0.9, push_opportunities=True)
    result = TeamCycleResult(
        trends=[
            TrendReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                strength=0.4,
                timeframe="daily",
                rationale="weak",
            )
        ]
    )
    notes = policy.evaluate_cycle(result)
    assert notes == []


def test_policy_skips_opportunities_in_dry_run_by_default():
    policy = NotificationPolicy(
        min_conviction=0.5,
        push_opportunities=True,
        dry_run=True,
        notify_dry_run=False,
    )
    result = TeamCycleResult(
        trends=[
            TrendReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                strength=0.8,
                timeframe="daily",
                rationale="strong",
            )
        ]
    )
    notes = policy.evaluate_cycle(result)
    assert notes == []


def test_policy_prefixes_sim_when_dry_run_notify_enabled():
    policy = NotificationPolicy(
        min_conviction=0.5,
        push_opportunities=True,
        dry_run=True,
        notify_dry_run=True,
    )
    result = TeamCycleResult(
        trends=[
            TrendReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                strength=0.8,
                timeframe="daily",
                rationale="strong",
            )
        ]
    )
    notes = policy.evaluate_cycle(result)
    assert len(notes) == 1
    assert notes[0].title.startswith("[SIM]")


def test_policy_sweep_skipped_in_dry_run():
    policy = NotificationPolicy(
        min_conviction=0.5,
        push_opportunities=True,
        dry_run=True,
        notify_dry_run=False,
    )
    trend = TrendReport(
        symbol="MSFT",
        direction=TrendDirection.UP,
        strength=0.9,
        timeframe="daily",
        rationale="setup",
    )
    notes = policy.evaluate_sweep([trend], None)
    assert notes == []
