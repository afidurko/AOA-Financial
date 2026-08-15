"""Jim — short-term technical analyst with predicted-path overlays."""

from __future__ import annotations

import json
import math

from aoa.agents.base import Agent, clamp_conviction
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import ShortTermReport, TrendDirection

_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {
            "type": "string",
            "enum": ["up", "down", "sideways", "unclear"],
        },
        "conviction": {"type": "number"},
        "horizon_bars": {"type": "integer"},
        "rationale": {"type": "string"},
        "indicator_flags": {"type": "array", "items": {"type": "string"}},
        "support": {"type": ["number", "null"]},
        "resistance": {"type": ["number", "null"]},
        "stop": {"type": ["number", "null"]},
        "expected_return": {"type": "number"},
    },
    "required": [
        "direction",
        "conviction",
        "horizon_bars",
        "rationale",
        "indicator_flags",
        "support",
        "resistance",
        "stop",
        "expected_return",
    ],
    "additionalProperties": False,
}

_ROLE = (
    "You are Jim, the short-term stock market analyst on an autonomous trading "
    "team. You specialize in near-term price action using a broad technical "
    "indicator toolkit (SMA/EMA alignment, RSI, MACD, Bollinger, ATR, volume). "
    "Characterize the next few bars (intraday to a few sessions): direction, "
    "calibrated conviction in [0,1], key support/resistance/stop levels, and "
    "expected_return as a fraction (e.g. 0.02 = +2%). Prefer actionable "
    "short-horizon reads. Do not invent indicator values not present in the input."
)


class JimAgent(Agent):
    name = "jim"
    display_name = "Jim"
    role = "Short-Term Technical Analyst"

    system_prompt = _ROLE

    def analyze_contexts(
        self, snapshots: dict[str, SymbolSnapshot]
    ) -> list[ShortTermReport]:
        return [self.analyze_symbol(snap) for snap in snapshots.values()]

    def analyze_symbol(self, snap: SymbolSnapshot) -> ShortTermReport:
        if snap.error or not snap.technicals:
            return ShortTermReport(
                symbol=snap.symbol,
                direction=TrendDirection.UNCLEAR,
                conviction=0.0,
                horizon_bars=5,
                rationale=f"No usable data ({snap.error or 'empty'}).",
            )

        closes = _closes(snap)
        prompt = (
            f"Symbol: {snap.symbol}\n"
            f"Quote: {json.dumps(snap.to_context()['quote'])}\n"
            f"Technicals: {json.dumps(snap.technicals, default=str)}\n"
            f"Recent closes (tail): {json.dumps(closes[-20:], default=str)}\n\n"
            "Produce a short-term technical read as JSON."
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)
        horizon = max(1, min(20, int(r.get("horizon_bars") or 5)))
        expected = float(r.get("expected_return") or 0.0)
        direction = TrendDirection(r["direction"])
        path = build_predicted_path(
            closes,
            direction=direction,
            expected_return=expected,
            horizon_bars=horizon,
        )
        return ShortTermReport(
            symbol=snap.symbol,
            direction=direction,
            conviction=clamp_conviction(r.get("conviction", 0.0)),
            horizon_bars=horizon,
            rationale=str(r.get("rationale", "")),
            indicator_flags=[str(x) for x in (r.get("indicator_flags") or [])],
            support=_opt_float(r.get("support")),
            resistance=_opt_float(r.get("resistance")),
            stop=_opt_float(r.get("stop")),
            predicted_path=path,
            expected_return=expected,
        )


def build_predicted_path(
    closes: list[float],
    *,
    direction: TrendDirection,
    expected_return: float,
    horizon_bars: int,
) -> list[dict]:
    """Deterministic forward path for chart overlay from last close + return."""
    if not closes:
        return []
    last = float(closes[-1])
    if last <= 0:
        return []
    # Blend stated expected return with a short momentum estimate.
    mom = 0.0
    if len(closes) >= 6 and closes[-6] > 0:
        mom = (closes[-1] / closes[-6]) - 1.0
    blend = 0.7 * expected_return + 0.3 * mom
    if direction is TrendDirection.SIDEWAYS:
        blend *= 0.25
    elif direction is TrendDirection.UNCLEAR:
        blend *= 0.1
    elif direction is TrendDirection.DOWN and blend > 0:
        blend = -abs(blend)
    elif direction is TrendDirection.UP and blend < 0:
        blend = abs(blend)

    # Mild vol for path curvature (ATR proxy from recent stdev).
    rets = []
    for i in range(1, min(len(closes), 21)):
        a, b = closes[-i - 1], closes[-i]
        if a > 0:
            rets.append(math.log(b / a))
    vol = (sum(x * x for x in rets) / len(rets)) ** 0.5 if rets else 0.01
    path: list[dict] = []
    for step in range(1, horizon_bars + 1):
        frac = step / horizon_bars
        drift = last * (1.0 + blend * frac)
        # Slight mean-reverting wiggle so the overlay is not a perfect line.
        wiggle = last * vol * 0.35 * math.sin(frac * math.pi)
        price = round(drift + wiggle, 4)
        path.append({"step": step, "price": price})
    return path


def _closes(snap: SymbolSnapshot) -> list[float]:
    bars = snap.bars or snap.bars_by_timeframe.get("1Day") or []
    out = [float(b.close) for b in bars if getattr(b, "close", None)]
    if out:
        return out
    # Fall back to last_close from technicals when bar history is thin.
    last = snap.last_close()
    return [float(last)] if last else []


def _opt_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
