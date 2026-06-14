"""Tests for the risk-correctness behaviors: protective stops, the re-entry
guard, and that protective legs reach the broker order."""

from __future__ import annotations

from conftest import make_position

from aoa.brokerage.models import AssetClass, Order, Side
from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.swarm.orchestrator import Orchestrator


def _config(dry_run=False):
    return Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=dry_run,
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )


def test_equity_entry_gets_protective_stop(fake_broker, fake_llm, tmp_path):
    orch = Orchestrator(_config(), fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    result = orch.run_cycle()

    prop = result.blackboard.proposals[0]
    assert prop.side is Side.BUY and prop.asset_class is AssetClass.EQUITY
    # A protective stop always exists and sits below the entry price.
    assert prop.stop_price is not None and prop.stop_price < prop.est_price
    # Take-profit sits above entry.
    assert prop.take_profit_price is not None and prop.take_profit_price > prop.est_price


def test_protective_legs_reach_the_broker_order(fake_broker, fake_llm, tmp_path):
    orch = Orchestrator(_config(), fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    orch.run_cycle()

    assert len(fake_broker.submitted) == 1
    req = fake_broker.submitted[0]
    assert req.stop_loss_price is not None
    assert req.take_profit_price is not None
    assert req.is_protected is True


def test_reentry_guard_skips_existing_position(fake_broker, fake_llm, tmp_path):
    fake_broker.set_positions([make_position("AAPL", qty=10, price=100.0)])
    orch = Orchestrator(_config(), fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    result = orch.run_cycle()

    # PM still proposes AAPL, but the re-entry guard drops the buy before sizing.
    assert result.blackboard.proposals == []
    assert fake_broker.submitted == []


def test_reentry_guard_skips_pending_order(fake_broker, fake_llm, tmp_path):
    fake_broker.set_open_orders(
        [Order(id="o1", symbol="AAPL", qty=5, side=Side.BUY, status="new")]
    )
    orch = Orchestrator(_config(), fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    result = orch.run_cycle()

    assert result.blackboard.proposals == []
    assert fake_broker.submitted == []
