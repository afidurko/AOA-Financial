"""Integration tests: example-hftish patterns → Julie / Morgan / CLI / quotes."""

from __future__ import annotations

from aoa.brokerage.models import Quote
from aoa.data.market_data import SymbolSnapshot
from aoa.research.hftish_patterns import (
    Side,
    diagnose_quote_book,
    diagnose_snapshot_quote,
    synthetic_smoke,
)
from aoa.team.julie import JulieAgent, _book_diagnosis
from aoa.team.models import TrendDirection, TrendReport
from aoa.team.morgan import MorganAgent, _book_imbalance_baseline


def _snap_with_sizes(*, bid_size: float, ask_size: float) -> SymbolSnapshot:
    return SymbolSnapshot(
        symbol="SNAP",
        quote=Quote(
            symbol="SNAP",
            bid=10.01,
            ask=10.02,
            bid_size=bid_size,
            ask_size=ask_size,
        ),
        technicals={
            "1Day": {
                "last_close": 10.01,
                "volume_metrics": {"volume_ratio": 1.0},
            }
        },
    )


def test_snapshot_context_includes_quote_sizes():
    snap = _snap_with_sizes(bid_size=500, ask_size=100)
    q = snap.to_context()["quote"]
    assert q["bid_size"] == 500
    assert q["ask_size"] == 100


def test_diagnose_quote_book_buy_pressure():
    diag = diagnose_quote_book(10.01, 10.02, 500, 100)
    assert diag.available
    assert diag.side is Side.BUY
    assert diag.signal and diag.signal.startswith("book_imbalance:buy")
    quote = _snap_with_sizes(bid_size=500, ask_size=100).quote
    assert diagnose_snapshot_quote(quote).side is Side.BUY


def test_julie_appends_book_imbalance_signal(fake_llm):
    snap = _snap_with_sizes(bid_size=500, ask_size=100)
    assert _book_diagnosis(snap)["available"] is True

    def respond(system, prompt, schema, **kwargs):
        assert "book-imbalance hints" in prompt
        assert "bid_size" in prompt
        return {
            "validated": True,
            "adjusted_strength": 0.7,
            "method_notes": "MA/RSI ok",
            "signals": ["rsi_neutral"],
        }

    fake_llm.structured = respond
    trend = TrendReport(
        symbol="SNAP",
        direction=TrendDirection.UP,
        strength=0.6,
        timeframe="1Day",
        rationale="up",
    )
    report = JulieAgent(fake_llm).refine(trend, snap)
    assert any(s.startswith("book_imbalance:buy") for s in report.signals)
    assert "rsi_neutral" in report.signals


def test_morgan_prompt_includes_book_hints(fake_llm):
    snap = _snap_with_sizes(bid_size=100, ask_size=500)
    assert _book_imbalance_baseline(snap)["side"] == "sell"
    captured: list[str] = []

    def capture(system, prompt, schema, **kwargs):
        captured.append(prompt)
        return {
            "volume_regime": "normal",
            "volume_ratio": 1.0,
            "liquidity_note": "ok",
            "options_volume_note": "n/a",
            "summary": "Ask-heavy tape.",
        }

    fake_llm.structured = capture
    report = MorganAgent(fake_llm, broker=None).analyze_symbol(snap)
    assert "book-imbalance hints" in captured[0]
    assert "Ask-heavy" in report.liquidity_note or "ask-heavy" in report.liquidity_note.lower()


def test_synthetic_smoke_ok():
    result = synthetic_smoke()
    assert result["ok"] is True
    assert result["never_live"] is True
    assert result["follow"]["side"] == "buy"
