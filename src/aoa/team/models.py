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


@dataclass(frozen=True)
class ApprovedSubTeam:
    """Approved sub-team roster loaded from analytics store."""

    lead_name: str
    team_name: str
    mission: str
    members: list[SubTeamMember]
    resolved_at: str = ""


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
class CatalystReport:
    """Hailey — news, catalysts, and event-risk read."""

    symbol: str
    catalyst_summary: str
    event_risk: str  # low | medium | high
    headline_sentiment: str  # bullish | bearish | neutral
    key_events: list[str] = field(default_factory=list)
    macro_note: str = ""
    impact_score: float = 0.0

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "catalyst_summary": self.catalyst_summary,
            "event_risk": self.event_risk,
            "headline_sentiment": self.headline_sentiment,
            "key_events": self.key_events,
            "macro_note": self.macro_note,
            "impact_score": round(self.impact_score, 2),
        }


@dataclass
class ShortTermReport:
    """Jim — short-term technical analysis with chart-overlay levels."""

    symbol: str
    direction: TrendDirection
    conviction: float  # 0.0–1.0
    horizon_bars: int
    rationale: str
    indicator_flags: list[str] = field(default_factory=list)
    support: float | None = None
    resistance: float | None = None
    stop: float | None = None
    predicted_path: list[dict] = field(default_factory=list)  # [{step, price}, ...]
    expected_return: float = 0.0

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "conviction": round(self.conviction, 2),
            "horizon_bars": self.horizon_bars,
            "rationale": self.rationale,
            "indicator_flags": self.indicator_flags,
            "support": self.support,
            "resistance": self.resistance,
            "stop": self.stop,
            "predicted_path": self.predicted_path,
            "expected_return": round(self.expected_return, 4),
        }


@dataclass
class CompanyAnalysisReport:
    """Cindy — company profitability / fair-value analysis with overlay bands."""

    symbol: str
    quality_score: float  # [-1, 1] profitability/quality composite
    fair_value: float | None
    upside_price: float | None
    downside_price: float | None
    expected_return: float
    conviction: float  # 0.0–1.0
    thesis: str
    math_notes: list[str] = field(default_factory=list)
    components: dict = field(default_factory=dict)
    profitability_grade: str = "n/a"  # A–F or n/a

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "quality_score": round(self.quality_score, 3),
            "fair_value": self.fair_value,
            "upside_price": self.upside_price,
            "downside_price": self.downside_price,
            "expected_return": round(self.expected_return, 4),
            "conviction": round(self.conviction, 2),
            "thesis": self.thesis,
            "math_notes": self.math_notes,
            "components": self.components,
            "profitability_grade": self.profitability_grade,
        }


@dataclass
class TradePlanLevels:
    """Andrea — concrete entry/exit levels for pre-execution review."""

    symbol: str
    action: str
    instrument: str  # equity | option | hedge | watch
    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    quantity: float
    est_cost: float
    max_risk_dollars: float
    reward_risk_ratio: float | None
    hedge_recommendation: str = ""
    options_analysis: str = ""
    pre_execution_note: str = ""

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "instrument": self.instrument,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "quantity": self.quantity,
            "est_cost": round(self.est_cost, 2),
            "max_risk_dollars": round(self.max_risk_dollars, 2),
            "reward_risk_ratio": self.reward_risk_ratio,
            "hedge_recommendation": self.hedge_recommendation,
            "options_analysis": self.options_analysis,
            "pre_execution_note": self.pre_execution_note,
        }


@dataclass
class RiskPlanReport:
    """Andrea — risk, hedging, and pre-execution trade plan with viz stats."""

    symbol: str
    summary: str
    approved_for_execution: bool
    plan: TradePlanLevels
    hedging: str = ""
    stats: dict = field(default_factory=dict)

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "summary": self.summary,
            "approved_for_execution": self.approved_for_execution,
            "plan": self.plan.to_context(),
            "hedging": self.hedging,
            "stats": self.stats,
        }


@dataclass
class OptionsVolumeHighlight:
    """Notable options activity at a strike/expiry."""

    expiration: str
    strike: float
    option_type: str  # call | put
    volume: float
    price: float
    open_interest: float = 0.0

    def to_context(self) -> dict:
        return {
            "expiration": self.expiration,
            "strike": self.strike,
            "option_type": self.option_type,
            "volume": self.volume,
            "price": self.price,
            "open_interest": self.open_interest,
        }


@dataclass
class MarketContextReport:
    """Morgan — volume, liquidity, and market-microstructure read."""

    symbol: str
    volume_regime: str  # elevated | normal | thin
    volume_ratio: float | None
    liquidity_note: str
    summary: str
    options_volume_note: str = ""
    options_highlights: list[OptionsVolumeHighlight] = field(default_factory=list)
    options_by_expiration: dict[str, float] = field(default_factory=dict)

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "volume_regime": self.volume_regime,
            "volume_ratio": self.volume_ratio,
            "liquidity_note": self.liquidity_note,
            "summary": self.summary,
            "options_volume_note": self.options_volume_note,
            "options_highlights": [h.to_context() for h in self.options_highlights],
            "options_by_expiration": self.options_by_expiration,
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
