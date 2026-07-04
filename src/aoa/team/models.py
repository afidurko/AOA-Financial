"""Shared types for the agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"
    UNCLEAR = "unclear"


@dataclass
class HealthCheck:
    name: str
    status: HealthStatus
    detail: str
    auto_fixed: bool = False

    def to_context(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "auto_fixed": self.auto_fixed,
        }


@dataclass
class HealthReport:
    checks: list[HealthCheck] = field(default_factory=list)
    can_proceed: bool = True
    summary: str = ""
    code_quality: dict | None = None

    @property
    def worst_status(self) -> HealthStatus:
        order = {HealthStatus.OK: 0, HealthStatus.DEGRADED: 1, HealthStatus.CRITICAL: 2}
        worst = HealthStatus.OK
        for c in self.checks:
            if order[c.status] > order[worst]:
                worst = c.status
        return worst

    def to_context(self) -> dict:
        return {
            "can_proceed": self.can_proceed,
            "summary": self.summary,
            "worst_status": self.worst_status.value,
            "checks": [c.to_context() for c in self.checks],
            "code_quality": self.code_quality,
        }


@dataclass
class TrendReport:
    symbol: str
    direction: TrendDirection
    strength: float  # 0.0–1.0
    timeframe: str
    rationale: str
    key_observations: list[str] = field(default_factory=list)

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "strength": round(self.strength, 2),
            "timeframe": self.timeframe,
            "rationale": self.rationale,
            "key_observations": self.key_observations,
        }


@dataclass
class AlgorithmReport:
    symbol: str
    validated: bool
    adjusted_strength: float
    method_notes: str
    signals: list[str] = field(default_factory=list)

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "validated": self.validated,
            "adjusted_strength": round(self.adjusted_strength, 2),
            "method_notes": self.method_notes,
            "signals": self.signals,
        }


@dataclass
class DecisionBrief:
    recommendations: list[dict]
    summary: str
    confidence: float
    code_quality: dict | None = None

    def to_context(self) -> dict:
        ctx = {
            "recommendations": self.recommendations,
            "summary": self.summary,
            "confidence": round(self.confidence, 2),
        }
        if self.code_quality:
            ctx["code_quality"] = self.code_quality
        return ctx


@dataclass
class SubTeamMember:
    name: str
    role: str
    responsibilities: list[str] = field(default_factory=list)

    def to_context(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "responsibilities": self.responsibilities,
        }


@dataclass
class TeamExpansionProposal:
    """A lead's proposed sub-team promotion — requires user approval."""

    lead_name: str
    lead_role: str
    promotion_title: str
    team_name: str
    mission: str
    members: list[SubTeamMember] = field(default_factory=list)
    expansion_rationale: str = ""
    first_quarter_goals: list[str] = field(default_factory=list)
    proposal_id: str = ""
    status: str = "pending"

    def to_context(self) -> dict:
        return {
            "id": self.proposal_id,
            "lead_name": self.lead_name,
            "lead_role": self.lead_role,
            "promotion_title": self.promotion_title,
            "team_name": self.team_name,
            "mission": self.mission,
            "members": [m.to_context() for m in self.members],
            "expansion_rationale": self.expansion_rationale,
            "first_quarter_goals": self.first_quarter_goals,
            "status": self.status,
        }

    @classmethod
    def from_store_row(cls, row: dict) -> TeamExpansionProposal:
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            import json

            payload = json.loads(payload)
        members = [
            SubTeamMember(
                name=m.get("name", ""),
                role=m.get("role", ""),
                responsibilities=list(m.get("responsibilities") or []),
            )
            for m in payload.get("members") or []
        ]
        return cls(
            lead_name=row.get("lead_name", payload.get("lead_name", "")),
            lead_role=row.get("lead_role", payload.get("lead_role", "")),
            promotion_title=row.get("promotion_title", payload.get("promotion_title", "")),
            team_name=row.get("team_name", payload.get("team_name", "")),
            mission=row.get("mission", payload.get("mission", "")),
            members=members,
            expansion_rationale=payload.get("expansion_rationale", ""),
            first_quarter_goals=list(payload.get("first_quarter_goals") or []),
            proposal_id=row.get("id", ""),
            status=row.get("status", "pending"),
        )


@dataclass
class MarketContextReport:
    """Morgan — volume, liquidity, and market-microstructure read."""

    symbol: str
    volume_regime: str  # elevated | normal | thin
    volume_ratio: float | None
    liquidity_note: str
    summary: str

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "volume_regime": self.volume_regime,
            "volume_ratio": self.volume_ratio,
            "liquidity_note": self.liquidity_note,
            "summary": self.summary,
        }


class PriorityLevel(str, Enum):
    MUST = "must"
    SHOULD = "should"
    LATER = "later"


@dataclass
class PriorityItem:
    level: PriorityLevel
    title: str
    detail: str
    source: str = ""
    action_hint: str = ""

    def to_context(self) -> dict:
        return {
            "level": self.level.value,
            "title": self.title,
            "detail": self.detail,
            "source": self.source,
            "action_hint": self.action_hint,
        }


@dataclass
class AssistantBrief:
    """Alex — executive assistant prioritization for the user."""

    must_do: list[PriorityItem] = field(default_factory=list)
    should_do: list[PriorityItem] = field(default_factory=list)
    can_wait: list[PriorityItem] = field(default_factory=list)
    summary: str = ""
    focus: str = ""

    def to_context(self) -> dict:
        return {
            "must_do": [i.to_context() for i in self.must_do],
            "should_do": [i.to_context() for i in self.should_do],
            "can_wait": [i.to_context() for i in self.can_wait],
            "summary": self.summary,
            "focus": self.focus,
        }


@dataclass
class TeamMemberStatus:
    name: str
    role: str
    completed: bool
    notes: str = ""

    def to_context(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "completed": self.completed,
            "notes": self.notes,
        }


@dataclass
class CEOReport:
    team_status: list[TeamMemberStatus] = field(default_factory=list)
    user_notifications: list[str] = field(default_factory=list)
    fixes_applied: list[dict] = field(default_factory=list)
    iphone_notifications_sent: list[str] = field(default_factory=list)
    overall_ok: bool = True
    summary: str = ""

    def to_context(self) -> dict:
        return {
            "overall_ok": self.overall_ok,
            "summary": self.summary,
            "team_status": [m.to_context() for m in self.team_status],
            "user_notifications": self.user_notifications,
            "fixes_applied": self.fixes_applied,
            "iphone_notifications_sent": self.iphone_notifications_sent,
        }
