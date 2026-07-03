"""Tests for journal summarization and position-P&L aggregation."""

from __future__ import annotations

from conftest import make_position

from aoa.brokerage.models import AssetClass
from aoa.reporting import position_pnl, summarize_journal


def _journal_entries():
    return [
        {"ts": "t1", "event": "cycle.start", "equity": 100_000},
        {"ts": "t2", "event": "scanner.candidates", "candidates": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]},
        {
            "ts": "t3",
            "event": "risk.review",
            "proposals": [
                {"symbol": "AAPL", "approved": True, "risk_notes": ["OK"]},
                {"symbol": "MSFT", "approved": False, "risk_notes": ["Rejected: per-position cap"]},
            ],
        },
        {"ts": "t4", "event": "order.submitted", "symbol": "AAPL", "side": "buy"},
        {"ts": "t5", "event": "proposal.skipped", "symbol": "NVDA"},
        {"ts": "t6", "event": "order.error", "symbol": "TSLA"},
        {"ts": "t7", "event": "cycle.start", "equity": 101_000},
    ]


def test_summarize_counts_activity():
    s = summarize_journal(_journal_entries())
    assert s.cycles == 2
    assert s.candidates_total == 2
    assert s.orders_submitted == 1
    assert s.orders_by_side == {"buy": 1}
    assert s.errors == 1
    assert s.reentry_skips == 1
    assert s.first_ts == "t1" and s.last_ts == "t7"
    assert s.last_logged_equity == 101_000


def test_summarize_collects_blocked_reasons():
    s = summarize_journal(_journal_entries())
    assert ("MSFT", "Rejected: per-position cap") in s.blocked
    assert s.blocked_reason_counts == {"Rejected: per-position cap": 1}


def test_summarize_empty_journal():
    s = summarize_journal([])
    assert s.cycles == 0
    assert s.orders_submitted == 0
    assert s.blocked == []


def test_position_pnl_aggregates():
    positions = [
        make_position("AAPL", qty=10, price=100.0),
        make_position("MSFT", qty=5, price=200.0),
    ]
    # make_position sets unrealized_pl=0.0; override by constructing winners/losers.
    from dataclasses import replace

    positions = [
        replace(positions[0], unrealized_pl=250.0),
        replace(positions[1], unrealized_pl=-80.0),
    ]
    pnl = position_pnl(positions)
    assert pnl.n == 2
    assert pnl.unrealized_pl == 170.0
    assert pnl.winners == 1 and pnl.losers == 1
    assert pnl.best == ("AAPL", 250.0)
    assert pnl.worst == ("MSFT", -80.0)


def test_position_pnl_empty():
    pnl = position_pnl([])
    assert pnl.n == 0
    assert pnl.unrealized_pl == 0.0
    assert pnl.best is None and pnl.worst is None


def test_position_pnl_includes_options():
    positions = [make_position("AAPL250117C00100000", qty=1, asset_class=AssetClass.OPTION, price=2.0)]
    pnl = position_pnl(positions)
    assert pnl.n == 1
