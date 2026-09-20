"""Tests for decision analytics: agent scorecard, hit rates, stage latency, funnel."""

from __future__ import annotations

from aoa.analytics.insights import (
    agent_scorecard,
    analytics_summary,
    cycle_throughput,
    direction_sign,
    proposal_funnel,
    stage_latency,
)
from aoa.analytics.store import AnalyticsStore


def _seed(store: AnalyticsStore) -> None:
    """Three cycles. AAPL: 100 → 110 → 99. MSFT: 200 → 190 → 190."""
    runs = [
        ("r1", "2026-07-01T10:00:00+00:00", "2026-07-01T10:00:30+00:00", {"AAPL": 100, "MSFT": 200}),
        ("r2", "2026-07-01T11:00:00+00:00", "2026-07-01T11:01:00+00:00", {"AAPL": 110, "MSFT": 190}),
        ("r3", "2026-07-02T10:00:00+00:00", "2026-07-02T10:00:10+00:00", {"AAPL": 99, "MSFT": 190}),
    ]
    for run_id, start, end, prices in runs:
        store.record_cycle(
            run_id=run_id,
            started_at=start,
            completed_at=end,
            mode="dry-run",
            halted=run_id == "r3",
            halt_reason="broker" if run_id == "r3" else "",
            payload={},
        )
        store.insert_prices(run_id, prices)

    # Tom: r1 AAPL up (hit: 100→110), r1 MSFT up (miss: 200→190),
    #      r2 AAPL up (miss: 110→99), r2 MSFT down (flat: 190→190 → miss).
    store.insert_signals(
        "r1",
        [
            {"ticker": "AAPL", "agent": "Tom", "direction": "up", "conviction": 0.8},
            {"ticker": "MSFT", "agent": "Tom", "direction": "up", "conviction": 0.6},
            {"ticker": "AAPL", "agent": "Julie", "direction": "validated", "conviction": 0.7},
            {"ticker": "AAPL", "agent": "technical", "direction": "bullish", "conviction": 0.75},
        ],
    )
    store.insert_signals(
        "r2",
        [
            {"ticker": "AAPL", "agent": "Tom", "direction": "up", "conviction": 0.7},
            {"ticker": "MSFT", "agent": "Tom", "direction": "down", "conviction": 0.5},
            {"ticker": "MSFT", "agent": "technical", "direction": "bearish", "conviction": 0.6},
        ],
    )
    # r3 signals have no later price → unscored but still counted.
    store.insert_signals(
        "r3", [{"ticker": "AAPL", "agent": "Tom", "direction": "up", "conviction": 0.9}]
    )

    store.insert_proposals(
        "r1",
        [
            {"symbol": "AAPL", "side": "buy", "approved": True, "strategy": "long_equity",
             "est_notional": 5000},
            {"symbol": "MSFT", "side": "buy", "approved": False, "strategy": "long_equity",
             "est_notional": 4000},
        ],
    )
    store.insert_proposals(
        "r2",
        [{"symbol": "AAPL", "side": "sell", "approved": True, "strategy": "exit",
          "est_notional": 5500}],
    )

    for run_id, analyze_ms in (("r1", 1000.0), ("r2", 3000.0), ("r3", 2000.0)):
        store.insert_stage_metric(run_id, "analyze", analyze_ms)
        store.insert_stage_metric(run_id, "intake", 100.0)
    store.insert_stage_metric("r3", "execute", 0.0, skipped=True)


def test_direction_sign_vocabulary():
    assert direction_sign("bullish") == direction_sign("up") == direction_sign("BUY") == 1
    assert direction_sign("bearish") == direction_sign("down") == -1
    assert direction_sign("validated") == direction_sign(None) == direction_sign("normal") == 0


def test_agent_scorecard_hit_rates(tmp_path):
    store = AnalyticsStore(tmp_path / "a.sqlite")
    _seed(store)
    card = {row["agent"]: row for row in agent_scorecard(store)}

    tom = card["Tom"]
    assert tom["signals"] == 5
    assert tom["tickers"] == 2
    assert tom["long"] == 4 and tom["short"] == 1 and tom["neutral"] == 0
    assert tom["scored"] == 4  # r3 AAPL has no later price
    assert tom["hit_rate"] == 0.25  # only r1 AAPL (100→110) was right
    # signed returns: +10%, -5%, -10%, 0% → mean -1.25%
    assert tom["avg_signed_return_pct"] == -1.25
    assert tom["avg_conviction"] == 0.7

    tech = card["technical"]
    assert tech["scored"] == 2
    assert tech["hit_rate"] == 0.5  # AAPL bullish hit, MSFT bearish flat miss

    julie = card["Julie"]
    assert julie["neutral"] == 1 and julie["scored"] == 0 and julie["hit_rate"] is None
    store.close()


def test_stage_latency_percentiles(tmp_path):
    store = AnalyticsStore(tmp_path / "b.sqlite")
    _seed(store)
    by_stage = {row["stage"]: row for row in stage_latency(store)}
    analyze = by_stage["analyze"]
    assert analyze["runs"] == 3
    assert analyze["avg_ms"] == 2000.0
    assert analyze["p50_ms"] == 2000.0
    assert analyze["max_ms"] == 3000.0
    assert by_stage["execute"]["skipped"] == 1 and by_stage["execute"]["runs"] == 0
    # slowest first
    assert [r["stage"] for r in stage_latency(store)][0] == "analyze"
    store.close()


def test_proposal_funnel(tmp_path):
    store = AnalyticsStore(tmp_path / "c.sqlite")
    _seed(store)
    funnel = proposal_funnel(store)
    assert funnel["proposals"] == 3
    assert funnel["approved"] == 2
    assert funnel["approval_rate"] == 0.667
    assert funnel["approved_notional"] == 10500.0
    sides = {g["side"]: g for g in funnel["by_side"]}
    assert sides["buy"]["proposals"] == 2 and sides["buy"]["approved"] == 1
    assert sides["sell"]["approval_rate"] == 1.0
    strategies = {g["strategy"]: g for g in funnel["by_strategy"]}
    assert strategies["long_equity"]["approval_rate"] == 0.5
    store.close()


def test_cycle_throughput(tmp_path):
    store = AnalyticsStore(tmp_path / "d.sqlite")
    _seed(store)
    tp = cycle_throughput(store)
    assert tp["cycles"] == 3
    assert tp["halted"] == 1
    assert tp["halt_rate"] == 0.333
    assert tp["avg_wall_ms"] == round((30_000 + 60_000 + 10_000) / 3, 1)
    assert tp["cycles_per_day"] == 3.0  # 3 cycles across exactly 1 day
    assert tp["first"].startswith("2026-07-01") and tp["last"].startswith("2026-07-02")
    store.close()


def test_summary_on_empty_store_is_well_formed(tmp_path):
    store = AnalyticsStore(tmp_path / "e.sqlite")
    summary = analytics_summary(store)
    assert summary["agents"] == []
    assert summary["stages"] == []
    assert summary["funnel"]["proposals"] == 0
    assert summary["throughput"]["cycles"] == 0
    store.close()


def test_insert_prices_ignores_bad_values_and_upserts(tmp_path):
    store = AnalyticsStore(tmp_path / "f.sqlite")
    store.insert_prices("r1", {"aapl": 100.0, "BAD": 0, "NONE": None, "": 5})
    rows = store.rows("SELECT ticker, price FROM cycle_prices ORDER BY ticker")
    assert rows == [{"ticker": "AAPL", "price": 100.0}]
    store.insert_prices("r1", {"AAPL": 101.5})
    assert store.rows("SELECT price FROM cycle_prices")[0]["price"] == 101.5
    store.close()


def test_bridge_persists_prices_from_snapshots(tmp_path, fake_broker, fake_llm):
    from aoa.analytics.bridge import CycleAnalyticsBridge
    from aoa.config import Config, RiskLimits
    from aoa.journal.store import Journal
    from aoa.swarm.orchestrator import Orchestrator
    from aoa.team.orchestrator import TeamCycleResult

    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=True,
        analytics_db_path=tmp_path / "analytics.sqlite",
        journal_path=tmp_path / "j.jsonl",
        state_path=str(tmp_path / "state.json"),
        plasticity_path=tmp_path / "plasticity.json",
        risk=RiskLimits(),
    )
    orch = Orchestrator(cfg, fake_broker, fake_llm, Journal(cfg.journal_path))
    cycle = orch.run_cycle()
    bridge = CycleAnalyticsBridge.from_config(cfg)
    bridge.begin_cycle()
    run_id = bridge.persist_cycle(TeamCycleResult(cycle=cycle))
    prices = bridge.store.rows("SELECT ticker, price FROM cycle_prices WHERE run_id=?", (run_id,))
    assert prices == [{"ticker": "AAPL", "price": 100.0}]  # fake quote mid (99.5/100.5)
    bridge.store.close()
