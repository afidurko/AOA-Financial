"""Shared agent types and the base ``Agent`` class.

Agents are deliberately *narrow*: each owns one slice of the analysis and emits
structured output. The orchestrator wires them together over a blackboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from aoa.brokerage.models import AssetClass, Side
from aoa.llm.client import LLMClient


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class Signal:
    """A directional view on a symbol from a single agent."""

    symbol: str
    source: str  # agent name
    direction: Direction
    conviction: float  # 0.0–1.0
    rationale: str
    horizon: str = "swing"  # "intraday" | "swing" | "position"
    key_levels: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "direction": self.direction.value,
            "conviction": round(self.conviction, 2),
            "horizon": self.horizon,
            "rationale": self.rationale,
            "key_levels": self.key_levels,
            "tags": self.tags,
        }


@dataclass
class TradeProposal:
    """A concrete, actionable trade proposed by the portfolio manager.

    For options, ``symbol`` is the OCC option symbol and ``qty`` is contracts.
    """

    symbol: str
    asset_class: AssetClass
    side: Side
    qty: float
    rationale: str
    conviction: float = 0.5
    underlying: str | None = None
    limit_price: float | None = None
    strategy: str = ""  # e.g. "long_equity", "long_call", "covered_call"
    est_price: float = 0.0  # per-share/contract price used for sizing
    # Populated by the risk manager:
    approved: bool = False
    risk_notes: list[str] = field(default_factory=list)

    @property
    def est_notional(self) -> float:
        mult = 100 if self.asset_class is AssetClass.OPTION else 1
        return abs(self.qty) * self.est_price * mult

    def to_context(self) -> dict:
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "asset_class": self.asset_class.value,
            "side": self.side.value,
            "qty": self.qty,
            "strategy": self.strategy,
            "est_price": self.est_price,
            "est_notional": round(self.est_notional, 2),
            "conviction": round(self.conviction, 2),
            "rationale": self.rationale,
            "approved": self.approved,
            "risk_notes": self.risk_notes,
        }


class Agent:
    """Base class: holds the LLM client and a name."""

    name: str = "agent"
    system_prompt: str = "You are a disciplined markets analyst."

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm


def parse_direction(value: object) -> Direction:
    try:
        return Direction(str(value))
    except (ValueError, TypeError):
        return Direction.NEUTRAL


def clamp_conviction(value: object, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default
