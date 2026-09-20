"""Deterministic risk guardrails for a cash account."""

from __future__ import annotations

from typing import Any

__all__ = ["RiskGuards", "GuardDecision"]


def __getattr__(name: str) -> Any:
    if name in {"RiskGuards", "GuardDecision"}:
        from aoa.risk.guards import GuardDecision, RiskGuards

        return RiskGuards if name == "RiskGuards" else GuardDecision
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
