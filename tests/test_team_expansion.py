"""Tests for team promotion / sub-team expansion proposals."""

from __future__ import annotations

from aoa.analytics.store import AnalyticsStore
from aoa.config import Config, RiskLimits
from aoa.team.alex import AlexAgent
from aoa.team.expansion import LEAD_PROFILES, TeamExpansionService
from aoa.team.models import PriorityLevel, SubTeamMember, TeamExpansionProposal
from aoa.team.orchestrator import TeamOrchestrator


def test_upsert_and_resolve_team_expansion(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite")
    proposal = TeamExpansionProposal(
        lead_name="Bob",
        lead_role="Systems Health",
        promotion_title="Director of Reliability",
        team_name="Bob Desk",
        mission="Keep systems healthy.",
        members=[
            SubTeamMember("Blake", "Monitor", ["Heartbeat checks"]),
        ],
        expansion_rationale="Need parallel coverage.",
        first_quarter_goals=["Onboard Blake"],
    )
    pid = store.upsert_team_expansion(proposal)
    assert pid
    rows = store.list_team_expansions(status="pending")
    assert len(rows) == 1
    assert rows[0]["lead_name"] == "Bob"

    ok = store.update_team_expansion(pid, mission="Updated mission.")
    assert ok
    row = store.get_team_expansion(pid)
    assert row is not None
    assert row["mission"] == "Updated mission."

    assert store.resolve_team_expansion(pid, "approved")
    assert store.list_team_expansions(status="pending") == []
    store.close()


def test_propose_all_creates_seven_leads(tmp_path, fake_llm):
    store = AnalyticsStore(tmp_path / "a.sqlite")
    svc = TeamExpansionService(fake_llm, store)
    created = svc.propose_all()
    assert len(created) == len(LEAD_PROFILES)
    assert len(store.list_team_expansions(status="pending")) == len(LEAD_PROFILES)
    assert store.list_approvals(status="pending")
    store.close()


def test_replace_pending_per_lead(tmp_path, fake_llm):
    store = AnalyticsStore(tmp_path / "a.sqlite")
    svc = TeamExpansionService(fake_llm, store)
    first = svc.propose_all()
    second = svc.propose_all(replace_pending=True)
    assert len(first) == len(LEAD_PROFILES)
    assert len(second) == len(LEAD_PROFILES)
    assert len(store.list_team_expansions(status="pending")) == len(LEAD_PROFILES)
    store.close()


def test_assistant_flags_pending_promotions(tmp_path, fake_llm):
    store = AnalyticsStore(tmp_path / "a.sqlite")
    pid = store.upsert_team_expansion(
        TeamExpansionProposal(
            lead_name="Tom",
            lead_role="Trend Analyst",
            promotion_title="Director of Trends",
            team_name="Tom Desk",
            mission="More trend coverage.",
            members=[SubTeamMember("Taylor", "Scout", ["Daily scans"])],
        )
    )
    store.add_approval(
        kind="team_expansion",
        title="Tom's team: Tom Desk",
        summary="More trend coverage.",
        payload={"expansion_id": pid},
        proposal_id=f"exp-{pid}",
    )
    brief = AlexAgent(fake_llm).prioritize(analytics_store=store)
    assert any(i.source == "team_expansion" for i in brief.must_do)
    assert any(i.level is PriorityLevel.MUST for i in brief.must_do)
    store.close()


def test_orchestrator_propose_team_expansions(fake_broker, fake_llm, tmp_path):
    cfg = Config(
        anthropic_api_key="x",
        analytics_enabled=True,
        analytics_db_path=tmp_path / "a.sqlite",
        journal_path=tmp_path / "j.jsonl",
        risk=RiskLimits(),
    )
    team = TeamOrchestrator(cfg, fake_broker, fake_llm)
    proposals = team.propose_team_expansions()
    assert len(proposals) == len(LEAD_PROFILES)
    team.analytics.store.close()
