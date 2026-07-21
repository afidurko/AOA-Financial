"""Tests for Jim (short-term TA) and Cindy (company profitability) agents."""

from __future__ import annotations

from datetime import datetime, timezone

from aoa.brokerage.models import Bar, Quote
from aoa.data.market_data import SymbolSnapshot
from aoa.team.alan import AlanAgent, _adapt_recommendations
from aoa.team.cindy import CindyAgent, compute_profitability_quant
from aoa.team.jim import JimAgent, build_predicted_path
from aoa.team.models import (
    CompanyAnalysisReport,
    ShortTermReport,
    TrendDirection,
    TrendReport,
)
from aoa.team.overlay import build_chart_overlays


def _snap(symbol: str = "AAPL") -> SymbolSnapshot:
    bars = [
        Bar(
            timestamp=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
            open=95 + i * 0.4,
            high=96 + i * 0.4,
            low=94 + i * 0.4,
            close=95.5 + i * 0.4,
            volume=1_000_000,
        )
        for i in range(30)
    ]
    return SymbolSnapshot(
        symbol=symbol,
        quote=Quote(symbol=symbol, bid=107.0, ask=107.4),
        bars=bars,
        bars_by_timeframe={"1Day": bars},
        technicals={
            "1Day": {
                "last_close": bars[-1].close,
                "sma_20": 100.0,
                "rsi_14": 55.0,
                "macd": 0.4,
            }
        },
    )


def test_jim_short_term_report(fake_llm):
    report = JimAgent(fake_llm).analyze_symbol(_snap())
    assert isinstance(report, ShortTermReport)
    assert report.symbol == "AAPL"
    assert report.direction is TrendDirection.UP
    assert report.predicted_path
    assert report.predicted_path[0]["step"] == 1
    assert report.support == 98.0


def test_build_predicted_path_direction():
    closes = [100 + i for i in range(20)]
    path = build_predicted_path(
        closes,
        direction=TrendDirection.UP,
        expected_return=0.03,
        horizon_bars=5,
    )
    assert len(path) == 5
    assert path[-1]["price"] > closes[-1]


def test_cindy_company_report(fake_llm):
    report = CindyAgent(fake_llm).analyze_symbol(_snap())
    assert isinstance(report, CompanyAnalysisReport)
    assert report.symbol == "AAPL"
    assert report.profitability_grade == "B"
    assert report.fair_value == 105.0
    assert report.components


def test_cindy_quant_scaffold():
    quant = compute_profitability_quant(_snap())
    assert quant["fair_value"] is not None
    assert "components" in quant
    assert quant["notes"]


def test_alan_adapts_from_jim_cindy(fake_llm):
    alan = AlanAgent(fake_llm)
    brief = alan.aggregate(
        [
            TrendReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                strength=0.7,
                timeframe="swing",
                rationale="uptrend",
            )
        ],
        [],
        short_term_contexts=[
            ShortTermReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                conviction=0.8,
                horizon_bars=5,
                rationale="near-term bid",
                expected_return=0.03,
            )
        ],
        company_contexts=[
            CompanyAnalysisReport(
                symbol="AAPL",
                quality_score=0.4,
                fair_value=110.0,
                upside_price=118.0,
                downside_price=95.0,
                expected_return=0.05,
                conviction=0.7,
                thesis="undervalued quality",
            )
        ],
    )
    assert brief.recommendations
    rec = brief.recommendations[0]
    assert rec["symbol"] == "AAPL"
    assert "Jim" in rec.get("rationale", "") or "Cindy" in rec.get("rationale", "") or rec["conviction"] >= 0.7


def test_adapt_recommendations_corroboration():
    adapted = _adapt_recommendations(
        [
            {
                "symbol": "AAPL",
                "action": "consider_long",
                "conviction": 0.6,
                "rationale": "base",
            }
        ],
        [
            ShortTermReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                conviction=0.9,
                horizon_bars=5,
                rationale="path up",
                expected_return=0.04,
            )
        ],
        [
            CompanyAnalysisReport(
                symbol="AAPL",
                quality_score=0.5,
                fair_value=120.0,
                upside_price=130.0,
                downside_price=90.0,
                expected_return=0.08,
                conviction=0.8,
                thesis="cheap",
            )
        ],
    )
    assert adapted[0]["conviction"] > 0.6
    assert "corroboration" in adapted[0]["rationale"]


def test_chart_overlays_payload():
    snap = _snap()
    overlays = build_chart_overlays(
        snapshots={"AAPL": snap},
        short_term=[
            ShortTermReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                conviction=0.7,
                horizon_bars=3,
                rationale="up",
                predicted_path=[{"step": 1, "price": 110.0}],
            )
        ],
        company_analyses=[
            CompanyAnalysisReport(
                symbol="AAPL",
                quality_score=0.2,
                fair_value=108.0,
                upside_price=115.0,
                downside_price=100.0,
                expected_return=0.02,
                conviction=0.5,
                thesis="ok",
            )
        ],
    )
    assert len(overlays) == 1
    assert overlays[0]["symbol"] == "AAPL"
    assert overlays[0]["bars"]
    assert overlays[0]["jim"]["predicted_path"]
    assert overlays[0]["cindy"]["fair_value"] == 108.0
