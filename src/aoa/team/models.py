"""Shared types for the five-member agent team."""

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
