"""Tests for Morgan market and options volume analysis."""

from __future__ import annotations

from aoa.brokerage.models import OptionContract, OptionType, Quote
from aoa.data.market_data import SymbolSnapshot
from aoa.team.models import OptionsVolumeHighlight
from aoa.team.morgan import MorganAgent, _scan_options_volume, _volume_baseline


def test_volume_baseline_regime():
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99.0, ask=101.0),
        technicals={
            "1Day": {
                "last_close": 100.0,
                "volume_metrics": {"volume_ratio": 1.8, "latest_volume": 2_000_000},
            }
        },
    )
    baseline = _volume_baseline(snap)
    assert baseline["regime"] == "elevated"
    assert baseline["volume_ratio"] == 1.8


def test_options_volume_scan_groups_by_expiration(fake_broker):
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99.0, ask=101.0),
        technicals={"1Day": {"last_close": 100.0}},
    )
    scan = _scan_options_volume(fake_broker, snap)
    assert scan["available"] is True
    assert scan["by_expiration"]["2027-02-19"] > 0
    assert scan["by_expiration"]["2026-12-18"] > 0
    assert scan["highlights"]
    assert scan["highlights"][0]["volume"] > 0
    assert "expiration" in scan["highlights"][0]


def test_morgan_includes_options_context(fake_broker, fake_llm):
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99.0, ask=101.0),
        technicals={
            "1Day": {
                "last_close": 100.0,
                "volume_metrics": {"volume_ratio": 1.0},
            }
        },
    )
    captured: list[str] = []

    def capture(system, prompt, schema, **kwargs):
        captured.append(prompt)
        return {
            "volume_regime": "normal",
            "volume_ratio": 1.0,
            "liquidity_note": "ok",
            "options_volume_note": "Feb expiry active.",
            "summary": "Normal equity volume; options flow elevated at 105C.",
        }

    fake_llm.structured = capture
    report = MorganAgent(fake_llm, fake_broker).analyze_symbol(snap)
    assert report.options_volume_note
    assert report.options_highlights
    assert report.options_by_expiration
    assert "options volume hints" in captured[0].lower()
    assert isinstance(report.options_highlights[0], OptionsVolumeHighlight)


def test_morgan_without_broker_skips_options(fake_llm):
    snap = SymbolSnapshot(
        symbol="AAPL",
        quote=Quote(symbol="AAPL", bid=99.0, ask=101.0),
        technicals={"1Day": {"last_close": 100.0, "volume_metrics": {"volume_ratio": 1.0}}},
    )
    report = MorganAgent(fake_llm, broker=None).analyze_symbol(snap)
    assert "No broker" in report.options_volume_note


def test_filter_chain_respects_strikes(fake_broker):
    chain = fake_broker.get_option_chain("AAPL") + [
        OptionContract(
            symbol="AAPL250117C00200000",
            underlying="AAPL",
            option_type=OptionType.CALL,
            strike=200.0,
            expiration="2025-01-17",
            volume=9999,
        )
    ]
    from aoa.team.morgan import _filter_options_chain

    filtered = _filter_options_chain(chain, 100.0)
    assert all(c.strike <= 120 for c in filtered)
    assert not any(c.strike == 200.0 for c in filtered)
