"""Tests for analytics store and cycle bridge."""

from __future__ import annotations

from aoa.analytics.bridge import CycleAnalyticsBridge, new_run_id
from aoa.analytics.store import AnalyticsStore
from aoa.config import Config, RiskLimits
from aoa.team.models import DecisionBrief, HealthReport, TrendDirection, TrendReport


def test_analytics_store_cycle_and_roi(tmp_path):
    db = tmp_path / "a.sqlite"
    store = AnalyticsStore(db)
    run_id = new_run_id()
    store.record_cycle(
        run_id=run_id,
        started_at="2026-07-04T00:00:00+00:00",
        completed_at="2026-07-04T00:01:00+00:00",
        mode="dry-run",
        halted=False,
        halt_reason="",
        payload={"ok": True},
    )
    store.insert_signals(
        run_id,
        [{"ticker": "AAPL", "agent": "Tom", "direction": "up", "conviction": 0.8, "summary": "x"}],
    )
    store.insert_proposals(
        run_id,
        [{"symbol": "AAPL", "side": "buy", "approved": True, "est_notional": 1000}],
    )
    last = store.get_last_cycle()
    assert last is not None
    assert last["run_id"] == run_id
    assert len(last["signals"]) == 1
    roi = store.roi_summary()
    assert roi["cycles_recorded"] == 1
    assert roi["approved_proposals"] == 1
    store.close()


def test_approval_and_research_inbox(tmp_path):
    store = AnalyticsStore(tmp_path / "b.sqlite")
    aid = store.add_approval(kind="research", title="T", summary="S", payload={"x": 1})
    assert store.list_approvals(status="pending")[0]["id"] == aid
    assert store.resolve_approval(aid, "approved")
    rid = store.add_research_proposal(
        title="Paper",
        abstract="Abstract",
        source="semantic_scholar",
        source_url="https://example.com",
        technique="momentum",
        backtest_score=0.7,
    )
    assert store.list_research_proposals(status="pending")[0]["id"] == rid
    assert store.resolve_research_proposal(rid, "approved")
    store.close()


def test_cycle_bridge_persist(tmp_path, fake_broker, fake_llm):
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        dry_run=True,
        analytics_enabled=True,
        analytics_db_path=tmp_path / "analytics.sqlite",
        journal_path=tmp_path / "j.jsonl",
        risk=RiskLimits(),
    )
    bridge = CycleAnalyticsBridge.from_config(cfg)
    bridge.begin_cycle()

    from aoa.team.orchestrator import TeamCycleResult

    result = TeamCycleResult(
        trends=[
            TrendReport(
                symbol="AAPL",
                direction=TrendDirection.UP,
                strength=0.75,
                timeframe="daily",
                rationale="uptrend",
            )
        ],
        decision=DecisionBrief(recommendations=[], summary="ok", confidence=0.8),
        health=HealthReport(summary="ok", can_proceed=True, checks=[]),
    )
    run_id = bridge.persist_cycle(result)
    assert run_id
    last = bridge.store.get_last_cycle()
    assert last is not None
    assert any(s["agent"] == "Tom" for s in last["signals"])
