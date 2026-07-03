"""Tests for order execution behavior."""

from __future__ import annotations

from conftest import FakeBroker

from aoa.agents.base import TradeProposal
from aoa.brokerage.models import AssetClass, Order, Side
from aoa.execution.executor import Executor
from aoa.journal.store import Journal


def _approved_buy(symbol="AAPL", qty=10):
    prop = TradeProposal(
        symbol=symbol,
        asset_class=AssetClass.EQUITY,
        side=Side.BUY,
        qty=qty,
        rationale="test",
        est_price=100.0,
    )
    prop.approved = True
    return prop


def test_skips_duplicate_open_order(tmp_path):
    broker = FakeBroker()
    broker.set_open_orders(
        [
            Order(
                id="open-1",
                symbol="AAPL",
                qty=10,
                side=Side.BUY,
                status="accepted",
                asset_class=AssetClass.EQUITY,
            )
        ]
    )
    journal = Journal(tmp_path / "j.jsonl")
    executor = Executor(broker, journal, dry_run=False)

    report = executor.execute([_approved_buy()])

    assert len(report.submitted) == 0
    assert len(report.skipped) == 1
    assert "duplicate open order" in report.skipped[0]["reason"]
    assert len(broker.submitted) == 0


def test_submits_when_no_conflicting_open_order(tmp_path):
    broker = FakeBroker()
    journal = Journal(tmp_path / "j.jsonl")
    executor = Executor(broker, journal, dry_run=False)

    report = executor.execute([_approved_buy()])

    assert len(report.submitted) == 1
    assert len(broker.submitted) == 1
