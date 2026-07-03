"""Specialist agents.

Each agent is a narrow expert that converts one slice of the analysis into a
directional :class:`AgentSignal` (score in [-1, 1], confidence in [0, 1]). The
swarm later aggregates these. Keeping them independent makes the ensemble's
behaviour transparent and easy to extend — add an agent, register a weight.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _action(score: float) -> str:
    return "BUY" if score > 0.15 else "SELL" if score < -0.15 else "HOLD"


@dataclass
class AgentSignal:
    agent: str
    score: float           # [-1, 1] directional conviction
    confidence: float      # [0, 1]
    rationale: str = ""

    @property
    def action(self) -> str:
        return _action(self.score)

    def to_dict(self) -> dict:
        return {"agent": self.agent, "action": self.action,
                "score": round(self.score, 4),
                "confidence": round(self.confidence, 4),
                "rationale": self.rationale}


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# -- individual agents ----------------------------------------------------
def technical_agent(tech: dict) -> AgentSignal:
    score = 0.0
    bits: List[str] = []
    if tech.get("golden_cross") is True:
        score += 0.35; bits.append("50>200 SMA")
    elif tech.get("golden_cross") is False:
        score -= 0.35; bits.append("50<200 SMA")

    rsi = tech.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            score += 0.25; bits.append(f"RSI oversold ({rsi:.0f})")
        elif rsi > 70:
            score -= 0.25; bits.append(f"RSI overbought ({rsi:.0f})")

    hist = tech.get("macd_hist")
    if hist is not None:
        score += _clamp(hist * 5.0, -0.2, 0.2)
        bits.append("MACD+" if hist > 0 else "MACD-")

    mom = tech.get("mom_252d")
    if mom is not None:
        score += _clamp(mom, -0.25, 0.25)
        bits.append(f"12m mom {mom:+.0%}")

    vol = tech.get("annualized_vol", 0.2)
    confidence = _clamp(0.75 - max(0.0, vol - 0.3), 0.2, 0.9)
    return AgentSignal("technical", _clamp(score), confidence,
                       ", ".join(bits) or "neutral technicals")


def fundamental_agent(fund: dict) -> AgentSignal:
    comp = float(fund.get("composite", 0.0))
    notes = fund.get("notes", [])
    confidence = 0.4 + 0.4 * min(1.0, abs(comp) + (0.2 if notes else 0.0))
    rationale = "; ".join(notes[:3]) or f"composite {comp:+.2f}"
    return AgentSignal("fundamental", _clamp(comp), _clamp(confidence, 0.2, 0.9),
                       rationale)


def forecast_agent(fc: dict) -> AgentSignal:
    exp = float(fc.get("expected_return", 0.0))
    score = _clamp(exp * 10.0)
    conf = float(fc.get("confidence", 0.3))
    return AgentSignal("forecast", score, _clamp(conf, 0.1, 0.9),
                       f"{exp:+.1%} over {fc.get('horizon_days', 21)}d "
                       f"({fc.get('direction', 'flat')})")


def regime_agent(regime: dict) -> AgentSignal:
    bias = {"bull": 0.7, "recovery": 0.4, "sideways": 0.0,
            "correction": -0.4, "bear": -0.7}.get(regime.get("regime"), 0.0)
    conf = float(regime.get("regime_confidence", regime.get("confidence", 0.5)))
    return AgentSignal("regime", _clamp(bias), _clamp(conf, 0.2, 0.9),
                       f"{regime.get('regime', 'n/a')} regime")


def sentiment_agent(sentiment: float) -> AgentSignal:
    return AgentSignal("sentiment", _clamp(sentiment), 0.4 + 0.4 * abs(sentiment),
                       f"sentiment {sentiment:+.2f}")


def llm_agent(analyst: dict) -> AgentSignal:
    return AgentSignal(
        "llm", _clamp(float(analyst.get("conviction", 0.0))),
        _clamp(float(analyst.get("confidence", 0.3)), 0.1, 0.95),
        (analyst.get("thesis", "") or "")[:160],
    )


def run_agents(*, technical: dict, fundamental: dict, forecast: dict,
               regime: dict, sentiment: float,
               analyst: Optional[dict] = None) -> List[AgentSignal]:
    signals = [
        technical_agent(technical),
        fundamental_agent(fundamental),
        forecast_agent(forecast),
        regime_agent(regime),
        sentiment_agent(sentiment),
    ]
    if analyst is not None:
        signals.append(llm_agent(analyst))
    return signals
