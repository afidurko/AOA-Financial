"""Tests for approved sub-team runtime pipeline wiring."""

from __future__ import annotations

from aoa.analytics.store import AnalyticsStore
from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.team.models import SubTeamMember, TeamExpansionProposal
from aoa.team.orchestrator import TeamOrchestrator
from aoa.team.subteam import SubTeamRunner, load_approved_subteams


def _approve_tom_team(store: AnalyticsStore) -> str:
    proposal = TeamExpansionProposal(
        lead_name="Tom",
        lead_role="Trend Analyst",
        promotion_title="Director of Trends",
        team_name="Tom Desk",
        mission="Expand trend coverage.",
        members=[
            SubTeamMember("Taylor", "Swing Scout", ["Daily trend classification"]),
            SubTeamMember("Jordan", "Pattern Clerk", ["Timeframe alignment"]),
        ],
    )
    pid = store.upsert_team_expansion(proposal)
    store.resolve_team_expansion(pid, "approved")
    return pid


def test_load_approved_subteams(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite")
    _approve_tom_team(store)
    teams = load_approved_subteams(store)
    assert "Tom" in teams
    assert len(teams["Tom"].members) == 2
    store.close()


def test_subteam_runner_records_journal(tmp_path, fake_llm):
    from aoa.team.models import ApprovedSubTeam

    journal = Journal(tmp_path / "j.jsonl")
    team = ApprovedSubTeam(
        lead_name="Tom",
        team_name="Tom Desk",
        mission="Trend depth",
        members=[SubTeamMember("Taylor", "Scout", ["Daily scans"])],
    )
    runner = SubTeamRunner(fake_llm, journal, parallel=False)
    outputs = runner.run_members(team, "Symbol AAPL context", lead_slug="tom")
    assert outputs
    events = {e["event"] for e in journal.tail(10)}
    assert "team.tom.subteam.start" in events
    assert "team.tom.sub" in events


def test_pipeline_uses_approved_tom_subteam(fake_broker, fake_llm, tmp_path):
    store = AnalyticsStore(tmp_path / "analytics.sqlite")
    _approve_tom_team(store)
    journal = Journal(tmp_path / "j.jsonl")
    cfg = Config(
        anthropic_api_key="x",
        universe=("AAPL",),
        dry_run=True,
        analytics_enabled=True,
        analytics_db_path=tmp_path / "analytics.sqlite",
        journal_path=tmp_path / "j.jsonl",
        team_subagents_enabled=True,
        risk=RiskLimits(),
    )
    team = TeamOrchestrator(cfg, fake_broker, fake_llm, journal)
    trends, _, _ = team.run_team_brief()
    assert trends
    events = {e["event"] for e in journal.tail(30)}
    assert "team.tom.subteam.start" in events
    assert "team.tom.subteam.synthesis" in events
    store.close()


def test_pipeline_without_approved_subteams_unchanged(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    cfg = Config(
        anthropic_api_key="x",
        universe=("AAPL",),
        dry_run=True,
        analytics_enabled=True,
        analytics_db_path=tmp_path / "analytics.sqlite",
        journal_path=tmp_path / "j.jsonl",
        risk=RiskLimits(),
    )
    team = TeamOrchestrator(cfg, fake_broker, fake_llm, journal)
    trends, algorithms, decision = team.run_team_brief()
    assert trends and algorithms and decision.summary
    events = {e["event"] for e in journal.tail(30)}
    assert "team.tom.subteam.start" not in events
