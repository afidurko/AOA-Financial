"""Tests for the five-member agent team."""

from __future__ import annotations

from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.team.bob import BobAgent
from aoa.team.models import HealthStatus, TrendDirection
from aoa.team.orchestrator import TeamOrchestrator


def _config(dry_run=True):
    return Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=dry_run,
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )


def test_tom_knowledge_includes_finance_setup():
    from aoa.team.tom import TomAgent, KNOWLEDGE

    assert "shashankvemuri/Finance" in KNOWLEDGE
    assert "git clone https://github.com/shashankvemuri/Finance.git" in KNOWLEDGE
    assert "pip install -r requirements.txt" in KNOWLEDGE
    assert TomAgent.knowledge is KNOWLEDGE
    assert "Reference knowledge:" in TomAgent.system_prompt


def test_bob_health_passes(fake_broker):
    bob = BobAgent(_config(), fake_broker)
    report = bob.check_health()
    assert report.can_proceed is True
    assert report.worst_status is HealthStatus.OK
    names = {c.name for c in report.checks}
    assert {"configuration", "broker", "code_integrity", "indicator_pipeline", "code_quality"} <= names


def test_team_brief_pipeline(fake_broker, fake_llm):
    team = TeamOrchestrator(_config(), fake_broker, fake_llm)
    trends, algorithms, decision = team.run_team_brief()
    assert len(trends) == 1
    assert trends[0].symbol == "AAPL"
    assert trends[0].direction is TrendDirection.UP
    assert len(algorithms) == 1
    assert algorithms[0].validated is True
    assert decision.summary
    assert len(decision.recommendations) >= 1


def test_full_team_cycle(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "team.jsonl")
    team = TeamOrchestrator(_config(dry_run=True), fake_broker, fake_llm, journal)
    result = team.run_cycle()

    assert result.halted is False
    assert result.health is not None
    assert result.health.can_proceed
    assert result.ceo is not None
    assert result.ceo.overall_ok
    assert result.cycle is not None
    assert len(result.cycle.blackboard.proposals) == 1
    assert result.trends
    assert result.algorithms
    assert result.decision is not None

    events = {e["event"] for e in journal.tail(50)}
    assert "team.bob.health" in events
    assert "team.tom.trends" in events
    assert "team.julie.algorithms" in events
    assert "team.alan.decision" in events
    assert "team.aaron.review" in events


def test_aaron_escalates_on_critical_health(fake_broker, fake_llm):
    class BrokenBroker:
        name = "broken"

        def get_account(self):
            raise RuntimeError("down")

        def is_market_open(self):
            return True

    team = TeamOrchestrator(_config(), BrokenBroker(), fake_llm)  # type: ignore[arg-type]
    result = team.run_cycle()

    assert result.halted is True
    assert result.ceo is not None
    assert result.ceo.user_notifications
    assert result.cycle is None
