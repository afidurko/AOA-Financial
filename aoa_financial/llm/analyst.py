"""Deep-analysis analyst for the offline aoa_financial swarm.

Uses a local OpenAI-compatible server (WASTE) by default. Claude/Anthropic is
opt-in via ``AOA_LLM_PROVIDER=anthropic``. If no live backend is available,
a deterministic offline analyst produces the same JSON shape from the evidence
so the rest of the pipeline is never blocked. Set ``AOA_FORCE_OFFLINE=1`` to
force the offline path.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

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
    source: str                 # "openai_compatible" | "claude" | "offline"
    thesis: str
    action: str
    conviction: float
    confidence: float
    time_horizon: str
    key_drivers: list[str] = field(default_factory=list)
    key_risks: list[str] = field(default_factory=list)
    model: str | None = None

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
                   sentiment: float, sector: str) -> dict[str, Any]:
    """Assemble the compact evidence packet handed to the analyst."""
    return {
        "ticker": ticker,
        "sector": sector,
        "technical": technical,
        "fundamental": fundamental,
        "forecast": forecast,
        "regime": regime,
        "reverse_engineering": reverse,
        "sentiment": sentiment,
    }


class ClaudeAnalyst:
    """Name kept for call-site compatibility; prefers local WASTE by default."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def analyze(self, evidence: dict[str, Any]) -> AnalystResult:
        ticker = str(evidence.get("ticker", "UNKNOWN"))
        if self._can_use_live():
            try:
                return self._analyze_live(ticker, evidence)
            except Exception as exc:  # never let the LLM path break the run
                offline = self._analyze_offline(ticker, evidence)
                offline.key_risks.append(f"[live analyst unavailable: {exc}]")
                return offline
        return self._analyze_offline(ticker, evidence)

    def _can_use_live(self) -> bool:
        if os.environ.get("AOA_FORCE_OFFLINE") == "1":
            return False
        provider = (self.config.llm_provider or "openai_compatible").lower()
        if provider == "openai_compatible":
            return bool(self.config.llm_base_url)
        if provider == "anthropic":
            if not os.environ.get("ANTHROPIC_API_KEY") and not self.config.llm_api_key:
                return False
            try:
                import anthropic  # noqa: F401
                return True
            except Exception:
                return False
        return False

    def _analyze_live(self, ticker: str, evidence: dict[str, Any]) -> AnalystResult:
        provider = (self.config.llm_provider or "openai_compatible").lower()
        if provider == "openai_compatible":
            return self._analyze_openai(ticker, evidence)
        return self._analyze_anthropic(ticker, evidence)

    def _analyze_openai(self, ticker: str, evidence: dict[str, Any]) -> AnalystResult:
        user_content = (
            "Quantitative evidence packet (JSON):\n\n"
            + json.dumps(evidence, indent=2)
            + "\n\nProduce the investment view as JSON matching the required schema."
        )
        body = {
            "model": self.config.llm_model,
            "max_tokens": self.config.llm_max_tokens,
            "temperature": 0,
            "thinking_effort": self.config.llm_effort,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "aoa_analyst",
                    "schema": _OUTPUT_SCHEMA,
                    "strict": True,
                },
            },
        }
        url = f"{self.config.llm_base_url.rstrip('/')}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.llm_api_key or 'local'}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(
                f"openai_compatible analyst failed ({exc.code}): {detail}"
            ) from exc
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(
                f"openai_compatible analyst returned no choices: {payload!r}"
            )
        text = (choices[0].get("message") or {}).get("content") or "{}"
        if isinstance(text, list):
            text = "".join(
                part.get("text", "")
                for part in text
                if isinstance(part, dict)
            )
        data = json.loads(text)
        return self._normalize(
            ticker, "openai_compatible", data, model=self.config.llm_model
        )

    def _analyze_anthropic(self, ticker: str, evidence: dict[str, Any]) -> AnalystResult:
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.llm_api_key or None)
        user_content = (
            "Quantitative evidence packet (JSON):\n\n"
            + json.dumps(evidence, indent=2)
            + "\n\nProduce the investment view as JSON matching the required schema."
        )

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

    def _analyze_offline(self, ticker: str, evidence: dict[str, Any]) -> AnalystResult:
        """Synthesise a coherent view directly from the evidence numbers."""
        rev = evidence.get("reverse_engineering", {})
        fc = evidence.get("forecast", {})
        fund = evidence.get("fundamental", {})
        tech = evidence.get("technical", {})
        regime = evidence.get("regime", {})
        sentiment = evidence.get("sentiment", 0.0)

        bias = float(rev.get("forward_bias", 0.0))
        exp_ret = float(fc.get("expected_return", 0.0))
        fund_score = float(fund.get("composite", 0.0))

        conviction = max(-1.0, min(1.0,
                         0.45 * bias + 0.30 * (exp_ret * 8.0) + 0.25 * fund_score))
        if conviction > 0.2:
            action = "BUY"
        elif conviction < -0.2:
            action = "SELL"
        else:
            action = "HOLD"

        confidence = max(0.1, min(0.9,
                         0.5 * float(rev.get("explained_variance", 0.0))
                         + 0.3 * float(fc.get("confidence", 0.0))
                         + 0.2 * float(regime.get("regime_confidence", 0.0))))

        drivers: list[str] = []
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

    def _normalize(self, ticker: str, source: str, data: dict,
                   model: str | None) -> AnalystResult:
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
