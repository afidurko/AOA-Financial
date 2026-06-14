"""Tests for the risk-correctness behaviors: protective stops, the re-entry
guard, and that protective legs reach the broker order."""

from __future__ import annotations

from datetime import date

from conftest import FakeBroker, make_position

from aoa.brokerage.models import AssetClass, Order, Side
from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.state import StateStore
from aoa.swarm.orchestrator import Orchestrator


def _config(tmp_path, dry_run=False):
    return Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=dry_run,
        state_path=str(tmp_path / "state.json"),
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )


def test_equity_entry_gets_protective_stop(fake_broker, fake_llm, tmp_path):
    orch = Orchestrator(_config(tmp_path), fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    result = orch.run_cycle()

    prop = result.blackboard.proposals[0]
    assert prop.side is Side.BUY and prop.asset_class is AssetClass.EQUITY
    # A protective stop always exists and sits below the entry price.
    assert prop.stop_price is not None and prop.stop_price < prop.est_price
    # Take-profit sits above entry.
    assert prop.take_profit_price is not None and prop.take_profit_price > prop.est_price


def test_protective_legs_reach_the_broker_order(fake_broker, fake_llm, tmp_path):
    orch = Orchestrator(_config(tmp_path), fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    orch.run_cycle()

    assert len(fake_broker.submitted) == 1
    req = fake_broker.submitted[0]
    assert req.stop_loss_price is not None
    assert req.take_profit_price is not None
    assert req.is_protected is True


def test_reentry_guard_skips_existing_position(fake_broker, fake_llm, tmp_path):
    fake_broker.set_positions([make_position("AAPL", qty=10, price=100.0)])
    orch = Orchestrator(_config(tmp_path), fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    result = orch.run_cycle()

    # PM still proposes AAPL, but the re-entry guard drops the buy before sizing.
    assert result.blackboard.proposals == []
    assert fake_broker.submitted == []


def test_reentry_guard_skips_pending_order(fake_broker, fake_llm, tmp_path):
    fake_broker.set_open_orders(
        [Order(id="o1", symbol="AAPL", qty=5, side=Side.BUY, status="new")]
    )
    orch = Orchestrator(_config(tmp_path), fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    result = orch.run_cycle()

    assert result.blackboard.proposals == []
    assert fake_broker.submitted == []


def test_kill_switch_baseline_persists_across_restart(fake_llm, tmp_path):
    cfg = _config(tmp_path)
    # The day's baseline was set at $100k (e.g. before a restart).
    StateStore(cfg.state_path).starting_equity_for_today(100_000, date.today())

    # A fresh orchestrator (new process) now sees equity down 4% at $96k.
    broker = FakeBroker(equity=96_000, cash=96_000)
    orch = Orchestrator(cfg, broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    result = orch.run_cycle()

    # Daily-loss kill switch fires off the persisted baseline, not a fresh one.
    assert all(not p.approved for p in result.blackboard.proposals)
    assert any(
        "kill-switch" in n for p in result.blackboard.proposals for n in p.risk_notes
    )
    assert broker.submitted == []


def test_unsettled_proceeds_block_a_buy(fake_broker, fake_llm, tmp_path):
    cfg = _config(tmp_path)
    # $99k of today's sale proceeds are unsettled, leaving ~$1k truly available.
    StateStore(cfg.state_path).record_sale(99_000, date.today())

    orch = Orchestrator(cfg, fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    result = orch.run_cycle()

    prop = result.blackboard.proposals[0]
    assert prop.approved is False
    assert any("cash buffer" in n for n in prop.risk_notes)
    assert fake_broker.submitted == []
