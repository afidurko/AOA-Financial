"""Swarm aggregation and the end-to-end per-ticker analysis pipeline.

``decide`` fuses the specialist :class:`AgentSignal`s into one decision using
weight × confidence voting, then sizes a suggested portfolio weight from the
net conviction and its dispersion (disagreement shrinks the position).

``analyze_ticker`` is the convenience orchestrator that runs the whole stack
for one symbol: pull bars -> compute all analytics -> LLM analyst -> agents ->
decision, and (optionally) persists everything to the store.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import Config
from ..databases.store import MarketStore
from ..analysis import technical as TA
from ..analysis import fundamentals as FA
from ..analysis import forecast as FC
from ..analysis import regimes as RG
from ..analysis import sentiment as SENT
from ..analysis import series as S
from ..analysis.reverse_engineer import reverse_engineer
from ..llm.analyst import ClaudeAnalyst, build_evidence
from .agents import AgentSignal, run_agents


@dataclass
class SwarmDecision:
    ticker: str
    asof: str
    action: str
    conviction: float          # [-1, 1]
    confidence: float          # [0, 1]
    target_weight: float       # [0, 1]
    rationale: str
    signals: List[AgentSignal] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker, "asof": self.asof, "action": self.action,
            "conviction": round(self.conviction, 4),
            "confidence": round(self.confidence, 4),
            "target_weight": round(self.target_weight, 4),
            "rationale": self.rationale,
            "signals": [s.to_dict() for s in self.signals],
        }


def decide(ticker: str, signals: List[AgentSignal],
           config: Optional[Config] = None,
           asof: Optional[str] = None) -> SwarmDecision:
    config = config or Config()
    weights = config.swarm_weights
    asof = asof or datetime.now(timezone.utc).date().isoformat()

    # Weighted, confidence-scaled vote.
    num = 0.0
    den = 0.0
    for s in signals:
        w = weights.get(s.agent, 1.0) * s.confidence
        num += w * s.score
        den += w
    conviction = num / den if den else 0.0

    # Confidence = average agent confidence, penalised by disagreement.
    confs = [s.confidence for s in signals] or [0.0]
    scores = [s.score for s in signals] or [0.0]
    dispersion = statistics.pstdev(scores) if len(scores) > 1 else 0.0
    base_conf = sum(confs) / len(confs)
    confidence = max(0.05, min(0.99, base_conf * (1.0 - 0.5 * dispersion)))

    if conviction > 0.15:
        action = "BUY"
    elif conviction < -0.15:
        action = "SELL"
    else:
        action = "HOLD"

    # Position sizing: scale by |conviction| × confidence, shrink on
    # disagreement. Cap any single position at 15%.
    target_weight = 0.0
    if action == "BUY":
        target_weight = min(0.15, max(0.0, abs(conviction) * confidence * 0.25))

    rationale = _rationale(action, conviction, confidence, dispersion, signals)
    return SwarmDecision(ticker, asof, action, conviction, confidence,
                         target_weight, rationale, signals)


def _rationale(action, conviction, confidence, dispersion, signals) -> str:
    agree = [s.agent for s in signals if (s.score > 0) == (conviction > 0)
             and abs(s.score) > 0.1]
    dissent = [s.agent for s in signals if (s.score > 0) != (conviction > 0)
               and abs(s.score) > 0.1]
    parts = [f"{action} (conviction {conviction:+.2f}, confidence "
             f"{confidence:.0%}, dispersion {dispersion:.2f})."]
    if agree:
        parts.append(f"Supporting: {', '.join(agree)}.")
    if dissent:
        parts.append(f"Dissenting: {', '.join(dissent)}.")
    return " ".join(parts)


def evaluate(ticker: str, bars, *,
             fundamentals: Optional[dict] = None,
             stored_sentiment: Optional[float] = None,
             sector: str = "Unknown",
             config: Optional[Config] = None,
             horizon: int = 21,
             use_llm: bool = False,
             regime_state=None) -> SwarmDecision:
    """Run the analytics + swarm on an explicit bar slice (no store access).

    This is the lookahead-free core shared by the live pipeline and the
    backtester: it sees *only* the bars passed in. ``analyze_ticker`` wraps it
    with store IO; the backtester calls it on a truncated history.
    """
    config = config or Config()
    ticker = ticker.upper()
    if len(bars) < 60:
        raise ValueError(f"insufficient history for {ticker} ({len(bars)} bars)")

    closes = [b.close for b in bars]
    tech = TA.snapshot(bars).to_dict()
    fund = FA.score(fundamentals).to_dict()
    fc = FC.forecast(
        closes, horizon_days=horizon, weights=config.forecast_weights
    ).to_dict()
    rstate = regime_state or RG.classify(bars)
    regime = rstate.to_dict()
    sentiment = SENT.blended(stored_sentiment, S.log_returns(closes)[-21:])
    rev = reverse_engineer(ticker, bars, stored_sentiment=stored_sentiment)

    analyst_dict = None
    if use_llm:
        evidence = build_evidence(
            ticker, technical=tech, fundamental=fund, forecast=fc,
            regime=regime, reverse=rev.to_dict(), sentiment=sentiment,
            sector=sector)
        analyst_dict = ClaudeAnalyst(config).analyze(evidence).to_dict()

    signals = run_agents(technical=tech, fundamental=fund, forecast=fc,
                         regime=regime, sentiment=sentiment, analyst=analyst_dict)
    decision = decide(ticker, signals, config=config, asof=bars[-1].date)
    decision.evidence = {
        "technical": tech, "fundamental": fund, "forecast": fc,
        "regime": regime, "reverse_engineering": rev.to_dict(),
        "sentiment": round(sentiment, 4), "analyst": analyst_dict,
        "_regime_state": rstate,
    }
    return decision


def analyze_ticker(store: MarketStore, ticker: str, *,
                   config: Optional[Config] = None,
                   horizon: int = 21,
                   use_llm: bool = True,
                   run_id: Optional[str] = None,
                   persist: bool = True) -> SwarmDecision:
    """Run the full analysis stack for one ticker, with store IO + persistence."""
    config = config or Config()
    ticker = ticker.upper()
    bars = store.get_bars(ticker)
    if len(bars) < 60:
        raise ValueError(f"insufficient history for {ticker} "
                         f"({len(bars)} bars); ingest it first")

    sec = store.get_security(ticker)
    sector = sec.sector if sec else "Unknown"
    decision = evaluate(
        ticker, bars, fundamentals=store.latest_fundamentals(ticker),
        stored_sentiment=store.latest_sentiment(ticker), sector=sector,
        config=config, horizon=horizon, use_llm=use_llm)
    asof = bars[-1].date
    regime_state = decision.evidence.pop("_regime_state")

    # --- persistence -----------------------------------------------------
    if persist:
        run_id = run_id or f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
        store.upsert_regime(ticker, asof, regime_state.regime,
                            regime_state.confidence,
                            regime_state.annualized_vol,
                            regime_state.trend_strength)
        store.insert_signals(run_id, [
            {"run_id": run_id, "ticker": ticker, "asof": asof, **s.to_dict()}
            for s in decision.signals])
        store.insert_decision(run_id, {
            "run_id": run_id, "ticker": ticker, "asof": asof,
            "action": decision.action, "conviction": decision.conviction,
            "confidence": decision.confidence,
            "target_weight": decision.target_weight,
            "rationale": decision.rationale,
            "payload": json.dumps(decision.evidence),
        })
    return decision
