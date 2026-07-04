"""Team expansion — each lead proposes a sub-team for user approval."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from aoa.llm.client import LLMClient
from aoa.team.models import SubTeamMember, TeamExpansionProposal

if TYPE_CHECKING:
    from aoa.analytics.store import AnalyticsStore
    from aoa.journal.store import Journal

_SCHEMA = {
    "type": "object",
    "properties": {
        "promotion_title": {"type": "string"},
        "team_name": {"type": "string"},
        "mission": {"type": "string"},
        "expansion_rationale": {"type": "string"},
        "first_quarter_goals": {"type": "array", "items": {"type": "string"}},
        "members": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "responsibilities": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "role", "responsibilities"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "promotion_title",
        "team_name",
        "mission",
        "expansion_rationale",
        "first_quarter_goals",
        "members",
    ],
    "additionalProperties": False,
}

LEAD_PROFILES: tuple[dict[str, str], ...] = (
    {
        "name": "Bob",
        "role": "Systems Health & Code Integrity",
        "domain": "reliability, broker connectivity, journal integrity, CI health",
    },
    {
        "name": "Tom",
        "role": "Trend Analyst",
        "domain": "multi-timeframe trends, pattern recognition, market character",
    },
    {
        "name": "Julie",
        "role": "Algorithm Specialist",
        "domain": "signal validation, backtest gates, code clarity, method notes",
    },
    {
        "name": "Morgan",
        "role": "Market & Volume Analyst",
        "domain": "volume regimes, liquidity, unusual activity, microstructure",
    },
    {
        "name": "Alan",
        "role": "Decision Aggregator",
        "domain": "cross-agent synthesis, recommendation quality, confidence calibration",
    },
    {
        "name": "Aaron",
        "role": "CEO",
        "domain": "remediation, escalation, compliance, team coordination",
    },
    {
        "name": "Alex",
        "role": "Executive Assistant",
        "domain": "user priorities, approval routing, operational briefings",
    },
)

_SYSTEM = (
    "You are a lead on the AOA Financial autonomous trading team. You have been "
    "promoted to build a small specialist sub-team (2–4 members) under your "
    "direction. Propose realistic agent roles that expand capacity in your domain "
    "without overlapping other leads. Each member needs a distinct name, role, "
    "and 2–4 concrete responsibilities. This proposal goes to the human owner "
    "for approval — be specific and actionable, not generic."
)


@dataclass(frozen=True)
class TeamExpansionService:
    llm: LLMClient
    store: AnalyticsStore
    journal: Journal | None = None

    def propose_all(self, *, replace_pending: bool = True) -> list[TeamExpansionProposal]:
        """Each lead drafts a sub-team proposal; stored for user approval."""
        created: list[TeamExpansionProposal] = []
        workers = min(4, len(LEAD_PROFILES))

        def _one(profile: dict[str, str]) -> TeamExpansionProposal:
            proposal = self._propose_for_lead(profile)
            pid = self.store.upsert_team_expansion(
                proposal,
                replace_pending=replace_pending,
            )
            proposal.proposal_id = pid
            self.store.upsert_approval(
                kind="team_expansion",
                title=f"{proposal.lead_name}'s team: {proposal.team_name}",
                summary=proposal.mission[:240],
                payload={"expansion_id": pid, "lead": proposal.lead_name},
                proposal_id=f"exp-{pid}",
            )
            if self.journal:
                self.journal.record(
                    "team.expansion.proposed",
                    {"lead": proposal.lead_name, "id": pid, "team": proposal.team_name},
                )
            return proposal

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_one, p): p for p in LEAD_PROFILES}
            for fut in as_completed(futures):
                created.append(fut.result())
        created.sort(key=lambda p: p.lead_name)
        return created

    def _propose_for_lead(self, profile: dict[str, str]) -> TeamExpansionProposal:
        prompt = (
            f"Lead: {profile['name']} ({profile['role']})\n"
            f"Domain: {profile['domain']}\n\n"
            "Propose your promoted sub-team as JSON."
        )
        try:
            r = self.llm.structured(_SYSTEM, prompt, _SCHEMA)
            return _from_llm(profile, r)
        except Exception:  # noqa: BLE001
            return _fallback_proposal(profile)


def _from_llm(profile: dict[str, str], r: dict[str, Any]) -> TeamExpansionProposal:
    members = [
        SubTeamMember(
            name=str(m.get("name", "")),
            role=str(m.get("role", "")),
            responsibilities=[str(x) for x in (m.get("responsibilities") or [])],
        )
        for m in r.get("members") or []
    ]
    return TeamExpansionProposal(
        lead_name=profile["name"],
        lead_role=profile["role"],
        promotion_title=str(r.get("promotion_title", f"Director — {profile['name']}")),
        team_name=str(r.get("team_name", f"{profile['name']} Unit")),
        mission=str(r.get("mission", "")),
        members=members,
        expansion_rationale=str(r.get("expansion_rationale", "")),
        first_quarter_goals=[str(g) for g in (r.get("first_quarter_goals") or [])],
    )


def _fallback_proposal(profile: dict[str, str]) -> TeamExpansionProposal:
    name = profile["name"]
    templates: dict[str, list[SubTeamMember]] = {
        "Bob": [
            SubTeamMember("Blake", "Uptime Monitor", ["Broker heartbeat checks", "Journal tail audits"]),
            SubTeamMember("Riley", "Config Guard", [".env drift detection", "Profile validation"]),
        ],
        "Tom": [
            SubTeamMember("Taylor", "Swing Scout", ["Daily trend classification", "Pullback detection"]),
            SubTeamMember("Jordan", "Pattern Clerk", ["Chart pattern logging", "Timeframe alignment"]),
        ],
        "Julie": [
            SubTeamMember("Casey", "Signal Validator", ["Cross-check Tom reads", "Strength calibration"]),
            SubTeamMember("Quinn", "Backtest Runner", ["Historical tape replay", "Regression flags"]),
        ],
        "Morgan": [
            SubTeamMember("Skyler", "Volume Tracker", ["Unusual volume alerts", "20d ratio monitoring"]),
            SubTeamMember("Reese", "Liquidity Analyst", ["Spread checks", "Cash-account sizing hints"]),
        ],
        "Alan": [
            SubTeamMember("Drew", "Bull Advocate", ["Constructive case builder", "Conviction scoring"]),
            SubTeamMember("Sam", "Risk Advocate", ["Watch/avoid arguments", "Conflict flagging"]),
        ],
        "Aaron": [
            SubTeamMember("Jamie", "Remediation Lead", ["Auto-fix retries", "Escalation triage"]),
            SubTeamMember("Logan", "Compliance Clerk", ["Live-trading gate checks", "Audit notes"]),
        ],
        "Alex": [
            SubTeamMember("Parker", "Inbox Curator", ["Approval deduplication", "Priority tagging"]),
            SubTeamMember("Avery", "Brief Editor", ["Must/should/wait summaries", "Focus line drafting"]),
        ],
    }
    members = templates.get(name, [
        SubTeamMember("Scout", "Analyst", ["Support lead domain tasks"]),
    ])
    return TeamExpansionProposal(
        lead_name=name,
        lead_role=profile["role"],
        promotion_title=f"Director of {profile['role']}",
        team_name=f"{name} Desk",
        mission=f"Expand {profile['domain']} capacity under {name}.",
        members=members,
        expansion_rationale="Template proposal — edit before approving.",
        first_quarter_goals=["Onboard sub-team roles", "Integrate with swarm journal"],
    )
