"""Team analysis lanes: concurrency, deterministic journaling, single-shot remediation."""

from __future__ import annotations

import threading
import time

from aoa.config import Config, RiskLimits
from aoa.journal.store import Journal
from aoa.team.orchestrator import TeamAnalysis, TeamCycleResult, TeamOrchestrator
from tests.conftest import FakeLLM


def _config(tmp_path, *, parallel: bool) -> Config:
    return Config(
        broker="moomoo",
        anthropic_api_key="x",
        universe=("AAPL", "MSFT"),
        dry_run=True,
        team_parallel=parallel,
        parallel_workers=4,
        analytics_enabled=False,
        vault_sync_enabled=False,
        state_path=str(tmp_path / "state.json"),
        plasticity_path=tmp_path / "plasticity.json",
        journal_path=tmp_path / "j.jsonl",
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )


class ConcurrencyProbeLLM(FakeLLM):
    """Counts how many ``structured`` calls are in flight at once."""

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self.in_flight = 0
        self.peak = 0
        self.calls = 0

    def structured(self, system, prompt, schema, **kwargs):
        with self._lock:
            self.in_flight += 1
            self.calls += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            time.sleep(0.01)
            return super().structured(system, prompt, schema, **kwargs)
        finally:
            with self._lock:
                self.in_flight -= 1


def test_analysis_lanes_run_concurrently_when_team_parallel(fake_broker, tmp_path):
    llm = ConcurrencyProbeLLM()
    team = TeamOrchestrator(_config(tmp_path, parallel=True), fake_broker, llm)
    analysis = team.analyze(team.trading.market.snapshots(["AAPL", "MSFT"]))

    assert isinstance(analysis, TeamAnalysis)
    assert {t.symbol for t in analysis.trends} == {"AAPL", "MSFT"}
    assert len(analysis.algorithms) == 2
    assert len(analysis.market_contexts) == 2
    assert len(analysis.catalysts) == 2
    assert len(analysis.short_term) == 2
    assert len(analysis.company_analyses) == 2
    assert analysis.decision.recommendations
    assert llm.peak > 1, "independent analyst lanes should overlap"


def test_analysis_lanes_serialize_when_team_parallel_disabled(fake_broker, tmp_path):
    llm = ConcurrencyProbeLLM()
    team = TeamOrchestrator(_config(tmp_path, parallel=False), fake_broker, llm)
    team.analyze(team.trading.market.snapshots(["AAPL", "MSFT"]))
    assert llm.peak == 1


def test_lane_journal_order_is_deterministic(fake_broker, fake_llm, tmp_path):
    journal = Journal(tmp_path / "team.jsonl")
    team = TeamOrchestrator(_config(tmp_path, parallel=True), fake_broker, fake_llm, journal)
    team.analyze(team.trading.market.snapshots(["AAPL", "MSFT"]))
    events = [e["event"] for e in journal.read_all() if e["event"].startswith("team.")]
    assert events == [
        "team.bob.code_quality",
        "team.tom.trends",
        "team.julie.algorithms",
        "team.morgan.context",
        "team.hailey.catalysts",
        "team.jim.short_term",
        "team.cindy.company",
        "team.alan.decision",
    ]


class EmptyAlanLLM(FakeLLM):
    """Alan never recommends anything, which triggers Aaron's re-run path."""

    def __init__(self):
        super().__init__()
        self.alan_calls = 0

    def structured(self, system, prompt, schema, **kwargs):
        if frozenset(schema.get("required") or ()) == self._ALAN:
            self.alan_calls += 1
            return {"recommendations": [], "summary": "nothing yet", "confidence": 0.3}
        return super().structured(system, prompt, schema, **kwargs)


def test_remediation_reruns_a_lane_exactly_once(fake_broker, tmp_path):
    llm = EmptyAlanLLM()
    team = TeamOrchestrator(_config(tmp_path, parallel=False), fake_broker, llm)
    result = team.run_cycle()

    assert isinstance(result, TeamCycleResult)
    assert result.decision is not None
    # Initial Alan pass + one remediation re-run — not the re-run twice over.
    assert llm.alan_calls == 2
    assert result.ceo is not None
    assert any(f["target"] == "Alan" and f["action"] == "rerun" for f in result.ceo.fixes_applied)
