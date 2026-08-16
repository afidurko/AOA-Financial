"""Tests for Riley's econophysics quant desk interview round."""

from __future__ import annotations

from aoa.analytics.store import AnalyticsStore
from aoa.team.interview import (
    JPHYS_COMPLEXITY,
    QUANT_SEATS,
    SEED_CANDIDATES,
    QuantHireService,
    RileyAgent,
)
from aoa.team.models import HireRecommendation


def test_five_quant_seats_defined():
    assert len(QUANT_SEATS) == 5
    assert {s.seat_id for s in QUANT_SEATS} == set(SEED_CANDIDATES)
    assert "Complexity" in JPHYS_COMPLEXITY["title"]
    assert JPHYS_COMPLEXITY["issn"] == "2632-072X"


def test_riley_interviews_one_seat(fake_llm):
    seat = QUANT_SEATS[0]
    seed = SEED_CANDIDATES[seat.seat_id]
    card = RileyAgent(fake_llm).interview_seat(
        seat,
        candidate_name=seed["name"],
        candidate_background=seed["background"],
    )
    assert card.seat_id == seat.seat_id
    assert card.candidate_name
    assert 0.0 <= card.score <= 1.0
    assert card.recommendation is HireRecommendation.HIRE
    assert card.hire is True
    assert card.transcript_notes


def test_start_round_stores_five_scorecards(tmp_path, fake_llm):
    store = AnalyticsStore(tmp_path / "hire.sqlite")
    svc = QuantHireService(fake_llm, store)
    round_ = svc.start_round()
    assert round_.team_name == "Econophysics Quant Desk"
    assert len(round_.scorecards) == 5
    assert all(c.hire for c in round_.scorecards)
    assert store.get_latest_quant_hire_round() is not None
    pending = store.list_approvals(status="pending")
    assert any(a["kind"] == "quant_hire" for a in pending)
    latest = svc.latest_round()
    assert latest is not None
    assert latest.round_id == round_.round_id
    store.close()


def test_replace_pending_supersedes_prior_round(tmp_path, fake_llm):
    store = AnalyticsStore(tmp_path / "hire.sqlite")
    svc = QuantHireService(fake_llm, store)
    first = svc.start_round()
    second = svc.start_round(replace_pending=True)
    assert first.round_id != second.round_id
    rows = store.list_quant_hire_rounds()
    assert len(rows) == 2
    statuses = {r["id"]: r["status"] for r in rows}
    assert statuses[first.round_id] == "superseded"
    assert statuses[second.round_id] == "pending"
    store.close()
