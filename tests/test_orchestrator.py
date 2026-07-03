"""End-to-end swarm cycle test using the fake broker and fake LLM."""

from __future__ import annotations

from aoa.agents.base import Direction, Signal
from aoa.brokerage.models import Side
from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.swarm.orchestrator import Orchestrator, _combine, _marketable_limit


def _config(dry_run=False):
    return Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=dry_run,
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )


def test_full_cycle_submits_order(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    orch = Orchestrator(_config(dry_run=False), fake_broker, fake_llm, journal)

    result = orch.run_cycle()

    # PM proposed a $5,000 AAPL buy => 50 shares at mid 100; within caps => approved.
    assert len(result.blackboard.proposals) == 1
    prop = result.blackboard.proposals[0]
    assert prop.symbol == "AAPL"
    assert prop.side is Side.BUY
    assert prop.qty == 50
    assert prop.approved is True

    # It was actually submitted to the (fake) broker.
    assert len(fake_broker.submitted) == 1
    assert fake_broker.submitted[0].symbol == "AAPL"
    assert result.execution is not None
    assert len(result.execution.submitted) == 1


def test_dry_run_submits_nothing(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    orch = Orchestrator(_config(dry_run=True), fake_broker, fake_llm, journal)

    result = orch.run_cycle()

    assert len(result.blackboard.proposals) == 1
    assert len(fake_broker.submitted) == 0  # nothing sent to the broker
    assert result.execution.dry_run is True


def test_journal_records_cycle(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    orch = Orchestrator(_config(dry_run=True), fake_broker, fake_llm, journal)
    orch.run_cycle()
    events = {e["event"] for e in journal.tail(50)}
    assert "cycle.start" in events
    assert "portfolio.decision" in events
    assert "cycle.end" in events


def test_combine_corroborated_signals():
    tech = Signal("AAPL", "technical", Direction.BULLISH, 0.8, "x")
    fund = Signal("AAPL", "fundamental", Direction.BULLISH, 0.6, "y")
    direction, conv = _combine(tech, fund)
    assert direction is Direction.BULLISH
    assert conv > 0.8  # corroboration boosts conviction


def test_combine_conflicting_signals_discounts():
    tech = Signal("AAPL", "technical", Direction.BULLISH, 0.8, "x")
    fund = Signal("AAPL", "fundamental", Direction.BEARISH, 0.6, "y")
    direction, conv = _combine(tech, fund)
    assert direction is Direction.BULLISH  # technicals lead
    assert conv < 0.8  # but discounted


def test_marketable_limit_padding():
    assert _marketable_limit(100.0, Side.BUY) == 101.0
    assert _marketable_limit(100.0, Side.SELL) == 99.0


def test_empty_scanner_still_reviews_open_positions(fake_broker, fake_llm, tmp_path):
    from conftest import make_position

    fake_llm.candidates = []
    fake_broker.set_positions([make_position("AAPL", qty=50, price=100.0)])
    journal = Journal(tmp_path / "j.jsonl")
    orch = Orchestrator(_config(dry_run=True), fake_broker, fake_llm, journal)

    result = orch.run_cycle()

    assert "Scanner returned no candidates." in result.notes
    assert "AAPL" in result.blackboard.signals
    assert len(result.blackboard.signals["AAPL"]) >= 2


def test_daily_equity_baseline_persists_across_restarts(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    journal.save_daily_equity_baseline(__import__("datetime").date.today(), 100_000.0)
    fake_broker._account = fake_broker._account.__class__(
        equity=96_000,
        cash=96_000,
        buying_power=96_000,
        settled_cash=96_000,
        options_level=2,
    )
    orch = Orchestrator(_config(dry_run=True), fake_broker, fake_llm, journal)
    orch.run_cycle()
    assert orch._starting_equity == 100_000.0
