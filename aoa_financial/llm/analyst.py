"""Claude-powered deep-analysis analyst.

The analyst takes the *quant evidence* produced by the analysis layer and asks
Claude Opus 4.8 to synthesise an institutional-quality investment view:
a thesis, key risks, a directional call, conviction and confidence — returned
as validated structured JSON the swarm can consume.

Resilience: if the ``anthropic`` SDK is not installed or no API key is present,
a deterministic offline analyst produces the same JSON shape from the evidence
so the rest of the pipeline is never blocked. Set ``AOA_FORCE_OFFLINE=1`` to
force the offline path even when the SDK is available.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import Config

# JSON schema the analyst must return. Used both for the live structured-output
# request and to validate/normalise the offline analyst's output.
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thesis": {"type": "string"},
        "action": {"type": "string", "enum": ["BUY", "HOLD", "SELL"]},
        "conviction": {"type": "number"},        # [-1, 1]
        "confidence": {"type": "number"},        # [0, 1]
        "time_horizon": {"type": "string"},
        "key_drivers": {"type": "array", "items": {"type": "string"}},
        "key_risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["thesis", "action", "conviction", "confidence",
                 "key_drivers", "key_risks"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You are a rigorous buy-side equity analyst on a quantitative trading desk. "
    "You are given pre-computed quantitative evidence for a single security: "
    "technical indicators, a fundamental score, a probabilistic price forecast, "
    "an inferred market regime, a reverse-engineered factor decomposition, and "
    "a sentiment reading. Synthesise these into a disciplined investment view. "
    "Be specific and cite the evidence. Do not invent data not present in the "
    "input. Calibrate conviction to the strength and agreement of the evidence, "
    "and confidence to how much of the return variance the models actually "
    "explain. Respond ONLY with the requested JSON object."
)


@dataclass
class AnalystResult:
    ticker: str
    source: str                 # "claude" | "offline"
    thesis: str
    action: str
    conviction: float
    confidence: float
    time_horizon: str
    key_drivers: List[str] = field(default_factory=list)
    key_risks: List[str] = field(default_factory=list)
    model: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker, "source": self.source, "thesis": self.thesis,
            "action": self.action, "conviction": round(self.conviction, 4),
            "confidence": round(self.confidence, 4),
            "time_horizon": self.time_horizon,
            "key_drivers": self.key_drivers, "key_risks": self.key_risks,
            "model": self.model,
        }


def build_evidence(ticker: str, *, technical: dict, fundamental: dict,
                   forecast: dict, regime: dict, reverse: dict,
                   sentiment: float, sector: str) -> Dict[str, Any]:
    """Assemble the compact evidence packet handed to the analyst."""
    return {
        "ticker": ticker,
        "sector": sector,
        "technical": technical,
        "fundamental": fundamental,
        "forecast": forecast,
        "regime": regime,
        "reverse_engineering": reverse,
        "sentiment": round(sentiment, 4),
    }


class ClaudeAnalyst:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

    # -- public API -------------------------------------------------------
    def analyze(self, evidence: Dict[str, Any]) -> AnalystResult:
        ticker = evidence.get("ticker", "?")
        if self._can_use_live():
            try:
                return self._analyze_live(ticker, evidence)
            except Exception as exc:  # never let the LLM path break the run
                offline = self._analyze_offline(ticker, evidence)
                offline.key_risks.append(f"[live analyst unavailable: {exc}]")
                return offline
        return self._analyze_offline(ticker, evidence)

    # -- live (Claude) ----------------------------------------------------
    def _can_use_live(self) -> bool:
        if os.environ.get("AOA_FORCE_OFFLINE") == "1":
            return False
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except Exception:
            return False

    def _analyze_live(self, ticker: str, evidence: Dict[str, Any]) -> AnalystResult:
        import anthropic

        client = anthropic.Anthropic()
        user_content = (
            "Quantitative evidence packet (JSON):\n\n"
            + json.dumps(evidence, indent=2)
            + "\n\nProduce the investment view as JSON matching the required schema."
        )

        # Stream to stay well under request timeouts on long, high-effort
        # generations; collect the final message at the end.
        with client.messages.stream(
            model=self.config.llm_model,
            max_tokens=self.config.llm_max_tokens,
            system=_SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={
                "effort": self.config.llm_effort,
                "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
            },
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            final = stream.get_final_message()

        text = next((b.text for b in final.content if b.type == "text"), "{}")
        data = json.loads(text)
        return self._normalize(ticker, "claude", data, model=self.config.llm_model)

    # -- offline (deterministic) -----------------------------------------
    def _analyze_offline(self, ticker: str, evidence: Dict[str, Any]) -> AnalystResult:
        """Synthesise a coherent view directly from the evidence numbers.

        This is a faithful, explainable stand-in: it reaches the same
        conclusions a human would from the same dashboard, so the swarm gets a
        meaningful 'analyst' vote even with no API access.
        """
        rev = evidence.get("reverse_engineering", {})
        fc = evidence.get("forecast", {})
        fund = evidence.get("fundamental", {})
        tech = evidence.get("technical", {})
        regime = evidence.get("regime", {})
        sentiment = evidence.get("sentiment", 0.0)

        bias = float(rev.get("forward_bias", 0.0))
        exp_ret = float(fc.get("expected_return", 0.0))
        fund_score = float(fund.get("composite", 0.0))

        # Blend the standalone reads into a single conviction.
        conviction = max(-1.0, min(1.0,
                         0.45 * bias + 0.30 * (exp_ret * 8.0) + 0.25 * fund_score))
        if conviction > 0.2:
            action = "BUY"
        elif conviction < -0.2:
            action = "SELL"
        else:
            action = "HOLD"

        # Confidence reflects how much the models explain + forecast confidence.
        confidence = max(0.1, min(0.9,
                         0.5 * float(rev.get("explained_variance", 0.0))
                         + 0.3 * float(fc.get("confidence", 0.0))
                         + 0.2 * float(regime.get("regime_confidence", 0.0))))

        drivers: List[str] = []
        for d in rev.get("dominant_drivers", [])[:3]:
            drivers.append(f"factor:{d}")
        if tech.get("golden_cross"):
            drivers.append("technical:50/200 golden cross")
        if fund_score > 0.2:
            drivers.append("fundamentals:above-average quality/value")
        if abs(sentiment) > 0.3:
            drivers.append(f"sentiment:{'supportive' if sentiment > 0 else 'adverse'}")
        drivers.append(f"regime:{regime.get('regime', 'unknown')}")

        risks = list(rev.get("assumptions", []))[:2]
        if tech.get("rsi_14") and tech["rsi_14"] > 70:
            risks.append("overbought on RSI — pullback risk")
        if tech.get("rsi_14") and tech["rsi_14"] < 30:
            risks.append("oversold on RSI — possible falling-knife")
        if float(rev.get("risk_component", 0.0)) > 0.4:
            risks.append("elevated annualised volatility raises drawdown risk")
        if not risks:
            risks.append("model explanatory power is limited — treat as low conviction")

        thesis = self._offline_thesis(ticker, action, rev, fc, fund, regime, sentiment)
        return AnalystResult(
            ticker=ticker, source="offline", thesis=thesis, action=action,
            conviction=round(conviction, 4), confidence=round(confidence, 4),
            time_horizon=f"{fc.get('horizon_days', 21)} trading days",
            key_drivers=drivers, key_risks=risks, model=None,
        )

    @staticmethod
    def _offline_thesis(ticker, action, rev, fc, fund, regime, sentiment) -> str:
        dr = rev.get("drift_to_risk", 0.0)
        return (
            f"{ticker}: {action}. The series is currently in a "
            f"'{regime.get('regime', 'n/a')}' regime with risk-adjusted drift "
            f"(trend/risk) of {dr:+.2f}. Reverse-engineered drivers are "
            f"{', '.join(rev.get('dominant_drivers', [])) or 'inconclusive'}; "
            f"the ensemble forecast implies a {fc.get('expected_return', 0.0):+.1%} "
            f"move over {fc.get('horizon_days', 21)} sessions "
            f"({fc.get('direction', 'flat')}). Fundamentals score "
            f"{fund.get('composite', 0.0):+.2f} and sentiment reads "
            f"{sentiment:+.2f}. Net forward bias {rev.get('forward_bias', 0.0):+.2f}."
        )

    # -- shared normalisation --------------------------------------------
    def _normalize(self, ticker: str, source: str, data: dict,
                   model: Optional[str]) -> AnalystResult:
        def fnum(x, lo, hi, default=0.0):
            try:
                return max(lo, min(hi, float(x)))
            except (TypeError, ValueError):
                return default

        action = str(data.get("action", "HOLD")).upper()
        if action not in ("BUY", "HOLD", "SELL"):
            action = "HOLD"
        return AnalystResult(
            ticker=ticker, source=source,
            thesis=str(data.get("thesis", "")).strip(),
            action=action,
            conviction=fnum(data.get("conviction"), -1.0, 1.0),
            confidence=fnum(data.get("confidence"), 0.0, 1.0, 0.3),
            time_horizon=str(data.get("time_horizon", "21 trading days")),
            key_drivers=list(data.get("key_drivers", []))[:8],
            key_risks=list(data.get("key_risks", []))[:8],
            model=model,
        )
