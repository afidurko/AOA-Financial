"""Tests for journal-driven neuroplasticity memory."""

from __future__ import annotations

import json

from aoa.agents.base import TradeProposal
from aoa.brokerage.models import Account, AssetClass, Side
from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.plasticity.consolidate import consolidate
from aoa.plasticity.memory import PlasticMemory, load_memory, save_memory
from aoa.plasticity.store import PlasticityStore
from aoa.swarm.orchestrator import Orchestrator


def _config(**kwargs):
    defaults = dict(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=True,
        plasticity_enabled=True,
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )
    defaults.update(kwargs)
    return Config(**defaults)


def test_consolidate_extracts_llm_veto_lessons(tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    journal.record(
        "risk.review",
        {
            "proposals": [
                {
                    "symbol": "AAPL",
                    "approved": False,
                    "risk_notes": ["LLM veto: over-concentration in mega-cap tech"],
                }
            ]
        },
    )
    journal.record(
        "risk.review",
        {
            "proposals": [
                {
                    "symbol": "AAPL",
                    "approved": False,
                    "risk_notes": ["LLM veto: over-concentration in mega-cap tech"],
                }
            ]
        },
    )

    memory = consolidate(journal, PlasticMemory(), tail=50, max_lessons=5)

    assert any("AAPL" in lesson and "LLM-vetoed 2x" in lesson for lesson in memory.lessons)
    assert memory.symbol_trust["AAPL"] < 0


def test_consolidate_rewards_approved_symbols(tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    journal.record(
        "risk.review",
        {"proposals": [{"symbol": "MSFT", "approved": True, "risk_notes": []}]},
    )
    journal.record("order.dry_run", {"symbol": "MSFT", "side": "buy"})

    memory = consolidate(journal, PlasticMemory(), tail=50, max_lessons=5)

    assert memory.symbol_trust["MSFT"] > 0


def test_plasticity_store_persists_and_audits(tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    path = tmp_path / "plasticity.json"
    store = PlasticityStore(path, journal, enabled=True, tail=50, max_lessons=5)

    journal.record(
        "risk.review",
        {
            "proposals": [
                {
                    "symbol": "NVDA",
                    "approved": False,
                    "risk_notes": ["position exceeds cap"],
                }
            ]
        },
    )
    delta = store.consolidate()

    assert path.exists()
    reloaded = load_memory(path)
    assert reloaded.lessons
    assert delta["symbol_trust"]["NVDA"] < 0
    events = {e["event"] for e in journal.tail(10)}
    assert "plasticity.update" in events


def test_prompt_block_includes_lessons_and_trust():
    memory = PlasticMemory(
        lessons=["AAPL was LLM-vetoed 2x recently: concentration risk"],
        symbol_trust={"AAPL": -0.35, "MSFT": 0.15},
    )
    block = memory.to_prompt_block()

    assert "Persistent lessons" in block
    assert "AAPL was LLM-vetoed" in block
    assert "AAPL: -0.35" in block
    assert "MSFT: +0.15" in block


def test_portfolio_agent_receives_plasticity_context(fake_broker, fake_llm, tmp_path):
    from aoa.agents.portfolio import PortfolioManagerAgent

    captured: list[str] = []

    def capture_structured(system, prompt, schema, **kwargs):
        captured.append(prompt)
        return {"proposals": [], "portfolio_commentary": "flat"}

    fake_llm.structured = capture_structured
    agent = PortfolioManagerAgent(fake_llm)
    agent.decide(
        [],
        [],
        {"equity": 100_000},
        plasticity_context="Persistent lessons:\n- be cautious on AAPL",
    )

    assert captured
    assert "Cross-cycle memory" in captured[0]
    assert "be cautious on AAPL" in captured[0]


def test_risk_agent_receives_plasticity_context(fake_broker, fake_llm, tmp_path):
    from aoa.agents.risk import RiskManagerAgent

    captured: list[str] = []

    def capture_structured(system, prompt, schema, **kwargs):
        captured.append(prompt)
        return {"vetoes": [], "assessment": "ok"}

    fake_llm.structured = capture_structured
    agent = RiskManagerAgent(fake_llm, RiskLimits())
    prop = TradeProposal(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side=Side.BUY,
        qty=10,
        rationale="test",
        approved=True,
    )
    account = Account(
        equity=100_000,
        cash=100_000,
        buying_power=100_000,
        settled_cash=100_000,
        options_level=2,
    )
    agent.review(
        [prop],
        account,
        [],
        starting_equity=100_000,
        plasticity_context="Persistent lessons:\n- AAPL vetoed before",
    )

    assert captured
    assert "Cross-cycle memory" in captured[0]
    assert "AAPL vetoed before" in captured[0]


def test_full_cycle_records_plasticity_update(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    cfg = _config(
        plasticity_path=tmp_path / "plasticity.json",
        journal_path=tmp_path / "j.jsonl",
    )
    orch = Orchestrator(cfg, fake_broker, fake_llm, journal)
    orch.run_cycle()

    events = {e["event"] for e in journal.tail(80)}
    assert "plasticity.update" in events
    assert (tmp_path / "plasticity.json").exists()


def test_plasticity_disabled_skips_consolidation(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    cfg = _config(
        plasticity_enabled=False,
        plasticity_path=tmp_path / "plasticity.json",
        journal_path=tmp_path / "j.jsonl",
    )
    orch = Orchestrator(cfg, fake_broker, fake_llm, journal)
    orch.run_cycle()

    events = {e["event"] for e in journal.tail(80)}
    assert "plasticity.update" not in events
    assert not (tmp_path / "plasticity.json").exists()


def test_memory_round_trip(tmp_path):
    path = tmp_path / "plasticity.json"
    original = PlasticMemory(
        lessons=["lesson one"],
        symbol_trust={"AAPL": -0.2},
        cycles_consolidated=3,
        updated_at="2026-01-01T00:00:00+00:00",
    )
    save_memory(path, original)
    loaded = load_memory(path)
    assert loaded.lessons == ["lesson one"]
    assert loaded.symbol_trust["AAPL"] == -0.2
    assert loaded.cycles_consolidated == 3
    assert json.loads(path.read_text())["lessons"] == ["lesson one"]
