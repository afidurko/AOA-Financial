"""Meshing agent — synthesizes specialist signals into a cohesive view.

The meshing agent sits between per-symbol analysis (technical, fundamental,
scanner context) and downstream decision agents (options, portfolio).  It
replaces the hard-coded ``_combine()`` heuristic with an LLM-driven synthesis
that surfaces conflicts, corroboration, and a calibrated unified conviction.

A deterministic fallback preserves pipeline continuity when the LLM is
unavailable or returns unusable output.
"""

from __future__ import annotations

import json

from aoa.agents.base import Agent, Direction, Signal
from aoa.swarm.environment import MeshedView

_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "conviction": {"type": "number"},
        "horizon": {"type": "string", "enum": ["intraday", "swing", "position"]},
        "rationale": {"type": "string"},
        "corroboration": {
            "type": "string",
            "enum": ["strong", "mixed", "weak", "none"],
        },
        "conflicts": {"type": "array", "items": {"type": "string"}},
        "key_levels": {
            "type": "object",
            "additionalProperties": {"type": "number"},
        },
    },
    "required": ["direction", "conviction", "horizon", "rationale", "corroboration"],
    "additionalProperties": False,
}


class MeshingAgent(Agent):
    name = "meshing"
    system_prompt = (
        "You are the meshing agent for an autonomous trading swarm. You receive "
        "multiple specialist signals (technical, fundamental, scanner context) for "
        "a single symbol and produce ONE unified directional view.\n\n"
        "Rules:\n"
        "- Weigh corroboration: aligned specialists → higher conviction; conflicts "
        "→ lower conviction and explicit conflict notes.\n"
        "- Technicals may lead on timing, fundamentals on durability — explain the "
        "blend in your rationale.\n"
        "- Reserve conviction >0.7 for strong, multi-source agreement.\n"
        "- When signals are weak or contradictory, prefer neutral with low conviction.\n"
        "- Never invent data absent from the inputs.\n"
        "- Pull support/resistance/stops from technical key_levels when present."
    )

    def mesh(
        self,
        symbol: str,
        signals: list[Signal],
        *,
        scanner_reason: str = "",
        snapshot_context: dict | None = None,
    ) -> MeshedView:
        if not signals:
            return MeshedView(
                symbol=symbol,
                direction=Direction.NEUTRAL,
                conviction=0.0,
                rationale="No specialist signals to mesh.",
                corroboration="none",
            )

        source_ctx = [s.to_context() for s in signals]
        prompt = (
            f"Symbol: {symbol}\n"
            f"Scanner reason: {scanner_reason or 'n/a'}\n"
            f"Specialist signals: {json.dumps(source_ctx, default=str)}\n"
        )
        if snapshot_context:
            prompt += f"Market snapshot: {json.dumps(snapshot_context, default=str)}\n"
        prompt += "\nReturn the unified meshed view as JSON."

        try:
            r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
            levels = {k: v for k, v in (r.get("key_levels") or {}).items() if v is not None}
            return MeshedView(
                symbol=symbol,
                direction=Direction(r["direction"]),
                conviction=_clamp(r["conviction"]),
                rationale=r["rationale"],
                horizon=r.get("horizon", "swing"),
                conflicts=list(r.get("conflicts") or []),
                corroboration=r.get("corroboration", "mixed"),
                source_signals=source_ctx,
                key_levels=levels,
                tags=["meshed"],
            )
        except Exception:
            return _fallback_mesh(symbol, signals, source_ctx, scanner_reason)


def _fallback_mesh(
    symbol: str,
    signals: list[Signal],
    source_ctx: list[dict],
    scanner_reason: str,
) -> MeshedView:
    """Deterministic synthesis when the LLM path fails."""
    tech = next((s for s in signals if s.source == "technical"), None)
    fund = next((s for s in signals if s.source == "fundamental"), None)
    conflicts: list[str] = []

    if tech and fund:
        direction, conviction = _combine(tech, fund)
        if tech.direction != fund.direction and (
            tech.direction is not Direction.NEUTRAL and fund.direction is not Direction.NEUTRAL
        ):
            conflicts.append(
                f"technical={tech.direction.value} vs fundamental={fund.direction.value}"
            )
        corroboration = (
            "strong"
            if tech.direction == fund.direction and tech.direction is not Direction.NEUTRAL
            else "mixed"
            if tech.direction is not Direction.NEUTRAL or fund.direction is not Direction.NEUTRAL
            else "none"
        )
        levels = dict(tech.key_levels)
    elif tech:
        direction, conviction = tech.direction, tech.conviction
        corroboration = "weak"
        levels = dict(tech.key_levels)
    elif fund:
        direction, conviction = fund.direction, fund.conviction
        corroboration = "weak"
        levels = dict(fund.key_levels)
    else:
        direction, conviction = Direction.NEUTRAL, 0.0
        corroboration = "none"
        levels = {}

    rationale = f"Fallback mesh of {len(signals)} signal(s)"
    if scanner_reason:
        rationale += f"; scanner: {scanner_reason}"

    return MeshedView(
        symbol=symbol,
        direction=direction,
        conviction=conviction,
        rationale=rationale,
        horizon=tech.horizon if tech else (fund.horizon if fund else "swing"),
        conflicts=conflicts,
        corroboration=corroboration,
        source_signals=source_ctx,
        key_levels=levels,
        tags=["meshed", "fallback"],
    )


def _combine(tech: Signal, fund: Signal) -> tuple[Direction, float]:
    """Combine technical & fundamental signals into a single directional view."""
    if tech.direction == fund.direction and tech.direction is not Direction.NEUTRAL:
        return tech.direction, min(1.0, (tech.conviction + fund.conviction) / 1.6)
    if tech.direction is not Direction.NEUTRAL:
        return tech.direction, tech.conviction * 0.6
    return Direction.NEUTRAL, 0.0


def _clamp(v: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
