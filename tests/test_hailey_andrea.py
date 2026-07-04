"""Tests for Hailey and Andrea team agents."""

from __future__ import annotations

from aoa.brokerage.models import Quote
from aoa.data.market_data import SymbolSnapshot
from aoa.data.news import NewsItem, NullNewsFeed
from aoa.team.andrea import AndreaAgent
from aoa.team.hailey import HaileyAgent
from aoa.team.models import CatalystReport, DecisionBrief, TrendDirection, TrendReport


def test_hailey_catalyst_report(fake_llm):
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99.0, ask=101.0),
        technicals={"1Day": {"last_close": 100.0}},
    )
    report = HaileyAgent(fake_llm, NullNewsFeed()).analyze_symbol(snap, [])
    assert isinstance(report, CatalystReport)
    assert report.symbol == "AAPL"
    assert report.event_risk in {"low", "medium", "high"}


def test_hailey_with_headlines(fake_llm):
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99.0, ask=101.0),
        technicals={"1Day": {"last_close": 100.0}},
    )
    headlines = [
        NewsItem(
            headline="Apple beats earnings",
            summary="EPS beat",
            source="test",
            created_at="2025-01-01T00:00:00Z",
            symbols=("AAPL",),
        )
    ]
    report = HaileyAgent(fake_llm, NullNewsFeed()).analyze_symbol(snap, headlines)
    assert report.key_events


def test_andrea_risk_plan(fake_broker, fake_llm):
    from aoa.config import Config, RiskLimits

    cfg = Config(anthropic_api_key="x", risk=RiskLimits(max_position_pct=0.10))
    agent = AndreaAgent(fake_llm, fake_broker, cfg)
    decision = DecisionBrief(
        recommendations=[
            {
                "symbol": "AAPL",
                "action": "consider_long",
                "conviction": 0.7,
                "rationale": "Aligned setup",
            }
        ],
        summary="One candidate",
        confidence=0.7,
    )
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99.0, ask=101.0),
        technicals={"1Day": {"last_close": 100.0}},
    )
    plans = agent.analyze_plans(
        proposals=[],
        decision=decision,
        trends=[
            TrendReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                strength=0.7,
                timeframe="swing",
                rationale="uptrend",
            )
        ],
        algorithms=[],
        market_contexts=[],
        catalysts=[],
        snapshots={"AAPL": snap},
    )
    assert len(plans) == 1
    assert plans[0].plan.entry_price
    assert plans[0].stats.get("bar_low") is not None
