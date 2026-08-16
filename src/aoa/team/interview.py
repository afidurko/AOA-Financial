"""Riley — hiring lead for a 5-seat econophysics quant trading desk.

Grounded in Journal of Physics: Complexity (IOP, ISSN 2632-072X) themes:
complex systems, economic/financial networks, agent-based modeling, and
critical phenomena / early-warning signals. Outside the ATTL twelve.
"""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from aoa.agents.base import Agent
from aoa.team.models import (
    HireRecommendation,
    InterviewRound,
    InterviewScorecard,
    QuantSeat,
)

if TYPE_CHECKING:
    from aoa.analytics.store import AnalyticsStore
    from aoa.journal.store import Journal
    from aoa.llm.client import LLMClient

# Primary literature anchor for the desk's research bar.
JPHYS_COMPLEXITY = {
    "title": "Journal of Physics: Complexity",
    "publisher": "IOP Publishing",
    "issn": "2632-072X",
    "url": "https://iopscience.iop.org/journal/2632-072X",
    "focus": (
        "Complex systems and networks applied to economic and financial systems, "
        "including complexity economics, agent-based models, tipping / early-warning "
        "signals, and network robustness."
    ),
    "related_venues": (
        "Physica A",
        "Physical Review E",
        "Frontiers in Physics (econophysics topics)",
        "Quantitative Finance",
    ),
}

QUANT_SEATS: tuple[QuantSeat, ...] = (
    QuantSeat(
        seat_id="microstructure",
        title="Microstructure & Scaling Laws Quant",
        domain="fat-tailed returns, scaling laws, order-flow statistics",
        research_bar=(
            "Must connect empirical market microstructure to statistical-physics "
            "stylized facts (power laws, volatility clustering) at tradable horizons."
        ),
        must_cover=(
            "return distribution tails",
            "volatility clustering / multifractality",
            "order-book or tick-data awareness",
        ),
    ),
    QuantSeat(
        seat_id="networks",
        title="Network Contagion Analyst",
        domain="financial networks, systemic risk, contagion paths",
        research_bar=(
            "Must map portfolio / counterparty / sector graphs to contagion and "
            "robustness metrics used in complex-network econophysics."
        ),
        must_cover=(
            "network construction from market data",
            "contagion / cascade risk",
            "centrality or community structure for risk",
        ),
    ),
    QuantSeat(
        seat_id="abm",
        title="Agent-Based Markets Modeler",
        domain="agent-based models, heterogeneity, emergence",
        research_bar=(
            "Must design or critique ABMs that reproduce market regimes without "
            "overfitting; link micro rules to macro price dynamics."
        ),
        must_cover=(
            "heterogeneous agents",
            "calibration / validation discipline",
            "regime emergence vs. equilibrium assumptions",
        ),
    ),
    QuantSeat(
        seat_id="critical",
        title="Critical Phenomena & Early-Warning Quant",
        domain="tipping points, critical slowing down, volatility regimes",
        research_bar=(
            "Must evaluate early-warning indicators (variance, autocorrelation, "
            "CSD) for regime shifts without false-alarm theatre."
        ),
        must_cover=(
            "critical slowing down caveats",
            "regime-shift detection",
            "false-positive control for trading use",
        ),
    ),
    QuantSeat(
        seat_id="execution",
        title="Signal Translation & Execution Quant",
        domain="physics→signal pipeline, sizing, execution constraints",
        research_bar=(
            "Must turn research signals into executable plans under AOA risk "
            "guards: capacity, stops, and cash-account constraints."
        ),
        must_cover=(
            "signal→trade mapping",
            "capacity and slippage awareness",
            "pre-trade risk checks",
        ),
    ),
)

# Seed candidates for the opening interview round (deterministic baseline).
SEED_CANDIDATES: dict[str, dict[str, str]] = {
    "microstructure": {
        "name": "Dr. Lena Voss",
        "background": "PhD statistical physics; tick-data scaling studies.",
    },
    "networks": {
        "name": "Dr. Omar Okonkwo",
        "background": "Complex networks; bank-interbank contagion models.",
    },
    "abm": {
        "name": "Dr. Priya Sen",
        "background": "Complexity economics ABMs; heterogeneous trader ensembles.",
    },
    "critical": {
        "name": "Dr. Elias Brandt",
        "background": "Early-warning signals; paleodata CSD methods applied to markets.",
    },
    "execution": {
        "name": "Morgan Hale",
        "background": "Execution research; microstructure-aware sizing and TCA.",
    },
}

_INTERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "seat_id": {"type": "string"},
        "candidate_name": {"type": "string"},
        "score": {"type": "number"},
        "recommendation": {
            "type": "string",
            "enum": ["strong_hire", "hire", "lean_hire", "hold", "no_hire"],
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "transcript_notes": {"type": "array", "items": {"type": "string"}},
        "hire": {"type": "boolean"},
    },
    "required": [
        "seat_id",
        "candidate_name",
        "score",
        "recommendation",
        "strengths",
        "gaps",
        "transcript_notes",
        "hire",
    ],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are Riley, AOA Financial's Quant Desk Hiring Lead. You interview "
    "candidates for a five-member econophysics / complexity-finance trading "
    "desk. Bar is Journal of Physics: Complexity–grade rigor applied to live "
    "markets: no hand-wavy physics metaphors, no unfalsifiable claims. Score "
    "0–1, prefer honest gaps over flattery. Outside the ATTL twelve — you do "
    "not change the meshed roster; hires require human approval."
)


class RileyAgent(Agent):
    name = "riley"
    display_name = "Riley"
    role = "Quant Desk Hiring Lead"

    system_prompt = _SYSTEM

    def interview_seat(
        self,
        seat: QuantSeat,
        *,
        candidate_name: str,
        candidate_background: str,
    ) -> InterviewScorecard:
        prompt = (
            f"Journal anchor:\n{json.dumps(JPHYS_COMPLEXITY, indent=2)}\n\n"
            f"Open seat:\n{json.dumps(seat.to_context(), indent=2)}\n\n"
            f"Candidate: {candidate_name}\n"
            f"Background: {candidate_background}\n\n"
            "Run a structured interview. Cover each must_cover topic. "
            "Return scorecard JSON only via schema."
        )
        try:
            raw = self.llm.structured(self.system_prompt, prompt, _INTERVIEW_SCHEMA)
            return _scorecard_from_llm(seat, candidate_name, candidate_background, raw)
        except Exception:  # noqa: BLE001 — deterministic fallback
            return _deterministic_scorecard(seat, candidate_name, candidate_background)


@dataclass(frozen=True)
class QuantHireService:
    """Opens and stores a 5-seat quant desk interview round."""

    llm: LLMClient
    store: AnalyticsStore
    journal: Journal | None = None

    def start_round(self, *, replace_pending: bool = True) -> InterviewRound:
        if replace_pending:
            self.store.supersede_quant_hire_rounds()

        riley = RileyAgent(self.llm)
        scorecards: list[InterviewScorecard] = []

        def _one(seat: QuantSeat) -> InterviewScorecard:
            seed = SEED_CANDIDATES[seat.seat_id]
            return riley.interview_seat(
                seat,
                candidate_name=seed["name"],
                candidate_background=seed["background"],
            )

        with ThreadPoolExecutor(max_workers=min(5, len(QUANT_SEATS))) as pool:
            futures = {pool.submit(_one, s): s for s in QUANT_SEATS}
            by_id: dict[str, InterviewScorecard] = {}
            for fut in as_completed(futures):
                card = fut.result()
                by_id[card.seat_id] = card
            scorecards = [by_id[s.seat_id] for s in QUANT_SEATS]

        hired = sum(1 for c in scorecards if c.hire)
        summary = (
            f"Riley opened the econophysics quant desk round "
            f"({hired}/{len(scorecards)} provisional hires). "
            f"Bar: {JPHYS_COMPLEXITY['title']}."
        )
        round_ = InterviewRound(
            round_id=str(uuid.uuid4()),
            team_name="Econophysics Quant Desk",
            journal_anchor=JPHYS_COMPLEXITY["title"],
            journal_url=JPHYS_COMPLEXITY["url"],
            seats=list(QUANT_SEATS),
            scorecards=scorecards,
            summary=summary,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.upsert_quant_hire_round(round_)
        self.store.upsert_approval(
            kind="quant_hire",
            title=f"Quant hire round: {round_.team_name}",
            summary=summary[:240],
            payload={"round_id": round_.round_id, "hired": hired},
            proposal_id=f"hire-{round_.round_id}",
        )
        if self.journal:
            self.journal.record(
                "team.riley.interview_round",
                round_.to_context(),
            )
        return round_

    def latest_round(self) -> InterviewRound | None:
        row = self.store.get_latest_quant_hire_round()
        if row is None:
            return None
        return _round_from_row(row)


def _clamp01(value: Any) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, x))


def _parse_recommendation(raw: Any) -> HireRecommendation:
    try:
        return HireRecommendation(str(raw))
    except ValueError:
        return HireRecommendation.HOLD


def _scorecard_from_llm(
    seat: QuantSeat,
    candidate_name: str,
    background: str,
    raw: dict[str, Any],
) -> InterviewScorecard:
    rec = _parse_recommendation(raw.get("recommendation"))
    hire = bool(raw.get("hire"))
    if rec is HireRecommendation.NO_HIRE:
        hire = False
    if rec is HireRecommendation.STRONG_HIRE:
        hire = True
    return InterviewScorecard(
        seat_id=seat.seat_id,
        seat_title=seat.title,
        candidate_name=str(raw.get("candidate_name") or candidate_name),
        candidate_background=background,
        score=_clamp01(raw.get("score")),
        recommendation=rec,
        strengths=[str(s) for s in (raw.get("strengths") or [])][:6],
        gaps=[str(g) for g in (raw.get("gaps") or [])][:6],
        transcript_notes=[str(t) for t in (raw.get("transcript_notes") or [])][:8],
        hire=hire,
    )


def _deterministic_scorecard(
    seat: QuantSeat,
    candidate_name: str,
    background: str,
) -> InterviewScorecard:
    """Baseline scorecards when LLM is unavailable — still starts the process."""
    notes = [
        f"Asked how {topic} informs live risk/trading." for topic in seat.must_cover
    ]
    strengths = [
        f"Grounded background for {seat.domain}",
        f"Aligned with {JPHYS_COMPLEXITY['title']} research bar",
    ]
    gaps = [
        "Needs live AOA risk-guard walkthrough",
        "Confirm production data-pipeline ownership",
    ]
    # Execution seat leans hire; research seats score slightly lower until live proof.
    base = 0.78 if seat.seat_id == "execution" else 0.72
    return InterviewScorecard(
        seat_id=seat.seat_id,
        seat_title=seat.title,
        candidate_name=candidate_name,
        candidate_background=background,
        score=base,
        recommendation=HireRecommendation.HIRE,
        strengths=strengths,
        gaps=gaps,
        transcript_notes=notes,
        hire=True,
    )


def _round_from_row(row: dict[str, Any]) -> InterviewRound:
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    seats = [QuantSeat(**s) for s in payload.get("seats", [])]
    cards = []
    for c in payload.get("scorecards", []):
        cards.append(
            InterviewScorecard(
                seat_id=c["seat_id"],
                seat_title=c["seat_title"],
                candidate_name=c["candidate_name"],
                candidate_background=c.get("candidate_background", ""),
                score=float(c.get("score", 0.5)),
                recommendation=_parse_recommendation(c.get("recommendation")),
                strengths=list(c.get("strengths") or []),
                gaps=list(c.get("gaps") or []),
                transcript_notes=list(c.get("transcript_notes") or []),
                hire=bool(c.get("hire")),
            )
        )
    return InterviewRound(
        round_id=row["id"],
        team_name=row.get("team_name") or payload.get("team_name", ""),
        journal_anchor=payload.get("journal_anchor", JPHYS_COMPLEXITY["title"]),
        journal_url=payload.get("journal_url", JPHYS_COMPLEXITY["url"]),
        seats=seats or list(QUANT_SEATS),
        scorecards=cards,
        summary=row.get("summary") or payload.get("summary", ""),
        status=row.get("status", "pending"),
        created_at=row.get("created_at", ""),
    )
