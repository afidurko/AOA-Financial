"""Structured communication protocol inspired by TradingAgents (arXiv:2412.20138).

Analysts publish concise structured reports; debate outcomes are recorded as
structured entries in the swarm environment rather than unstructured chat logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalystReport:
    """Structured analyst report stored in the global agent state."""

    symbol: str
    analyst: str  # technical | fundamental | news | sentiment
    direction: str
    conviction: float
    summary: str
    key_points: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "analyst": self.analyst,
            "direction": self.direction,
            "conviction": round(self.conviction, 2),
            "summary": self.summary,
            "key_points": self.key_points,
            "metrics": self.metrics,
        }


@dataclass
class ResearchDebate:
    """Bull/bear debate outcome with facilitator verdict."""

    symbol: str
    bull_argument: str
    bear_argument: str
    rounds: list[dict[str, str]] = field(default_factory=list)
    prevailing_view: str = "neutral"
    conviction: float = 0.0
    rationale: str = ""

    def to_context(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bull_argument": self.bull_argument,
            "bear_argument": self.bear_argument,
            "rounds": self.rounds,
            "prevailing_view": self.prevailing_view,
            "conviction": round(self.conviction, 2),
            "rationale": self.rationale,
        }


@dataclass
class RiskDebate:
    """Risk-seeking / neutral / conservative debate on trader proposals."""

    perspectives: list[dict[str, str]] = field(default_factory=list)
    facilitator_summary: str = ""
    vetoes: list[dict[str, str]] = field(default_factory=list)

    def to_context(self) -> dict[str, Any]:
        return {
            "perspectives": self.perspectives,
            "facilitator_summary": self.facilitator_summary,
            "vetoes": self.vetoes,
        }


def report_from_signal(signal, *, analyst: str, summary: str = "", key_points: list | None = None) -> AnalystReport:
    return AnalystReport(
        symbol=signal.symbol,
        analyst=analyst,
        direction=signal.direction.value,
        conviction=signal.conviction,
        summary=summary or signal.rationale,
        key_points=key_points or [],
        metrics={"tags": list(signal.tags), "horizon": signal.horizon},
    )
