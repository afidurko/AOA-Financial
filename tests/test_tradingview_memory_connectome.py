"""Neural desk memory (Hebbian synapses) and the fly-brain connectome motor loop."""

from __future__ import annotations

import json

import pytest

from aoa.tradingview.connectome import (
    DN_CHANNELS,
    REGIONS,
    FlyConnectome,
    MarketSense,
    sense_from_features,
)
from aoa.tradingview.memory import DeskMemory, reward_from_metrics

# --------------------------------------------------------------------------- #
# reward
# --------------------------------------------------------------------------- #


def test_reward_is_bounded_and_needs_evidence() -> None:
    assert reward_from_metrics({"total_trades": 2, "sqn": 9.0, "profit_factor": 9.0}) == 0.0
    good = reward_from_metrics({"total_trades": 60, "sqn": 3.0, "profit_factor": 2.5, "max_drawdown_pct": -5.0})
    bad = reward_from_metrics({"total_trades": 60, "sqn": -2.5, "profit_factor": 0.4, "max_drawdown_pct": -45.0})
    assert -1.0 <= bad < 0 < good <= 1.0
    inf_pf = reward_from_metrics({"total_trades": 40, "sqn": 2.0, "profit_factor": float("inf"), "max_drawdown_pct": -2.0})
    assert 0 < inf_pf <= 1.0
    few = reward_from_metrics({"total_trades": 5, "sqn": 3.0, "profit_factor": 2.5, "max_drawdown_pct": -5.0})
    assert 0 < few < good  # less evidence → smaller reward


# --------------------------------------------------------------------------- #
# memory
# --------------------------------------------------------------------------- #


def test_learn_moves_weight_toward_reward_and_recall() -> None:
    m = DeskMemory(eta=0.5)
    assert m.recall("p", "aapl", "1D") == 0.0
    w1 = m.learn("p", "AAPL", "1D", 1.0)
    assert w1 == pytest.approx(0.5)
    w2 = m.learn("p", "aapl", "1D", 1.0, metrics={"sqn": 2.0, "total_trades": 20})
    assert w2 == pytest.approx(0.75)
    assert m.recall("p", "AAPL", "1D") == pytest.approx(0.75)
    row = m.synapses[DeskMemory.key("p", "AAPL", "1D")]
    assert row["samples"] == 2 and row["last_metrics"]["sqn"] == 2.0
    # rewards are clamped
    m.learn("p", "AAPL", "1D", 5.0)
    assert m.recall("p", "AAPL", "1D") <= 1.0
    m.learn("p", "AAPL", "1D", -5.0)
    assert m.recall("p", "AAPL", "1D") >= -1.0


def test_decay_and_prune_stale_synapses() -> None:
    m = DeskMemory(eta=1.0, decay=0.5)
    m.learn("p", "X", "1D", 0.8)
    m.decay_all()
    assert m.recall("p", "X", "1D") == pytest.approx(0.4)
    # tiny weight with many samples is pruned
    k = DeskMemory.key("p", "X", "1D")
    m.synapses[k]["weight"] = 1e-4
    m.synapses[k]["samples"] = 10
    m.decay_all()
    assert k not in m.synapses


def test_aggregates_lessons_and_context() -> None:
    m = DeskMemory(eta=1.0)
    m.learn("good", "AAPL", "1D", 0.9)
    m.learn("good", "MSFT", "1D", 0.7)
    m.learn("bad", "AAPL", "1", -0.8)
    pt = m.preset_trust()
    assert list(pt) == ["good", "bad"] and pt["good"] == pytest.approx(0.8)
    assert m.timeframe_trust()["1"] == pytest.approx(-0.8)
    assert m.symbol_trust()["AAPL"] == pytest.approx(0.05, abs=1e-6)
    assert m.best_edges(1)[0]["symbol"] == "AAPL" and m.worst_edges(1)[0]["preset"] == "bad"
    lessons = m.distill_lessons()
    assert any("good" in text and "strongest" in text for text in lessons)
    assert any("bad" in text and "losing trust" in text for text in lessons)
    assert any("Avoid bad on AAPL@1" in text for text in lessons)
    ctx = m.to_context()
    assert ctx["synapses"] == 3 and ctx["preset_trust"] == pt
    block = m.to_prompt_block()
    assert "Preset trust" in block and "good" in block
    assert DeskMemory().to_prompt_block() == ""


def test_lessons_dedupe_across_runs_when_only_weight_changes() -> None:
    m = DeskMemory(eta=1.0)
    m.learn("bad", "AAPL", "1", -0.8)
    m.distill_lessons()
    first = [t for t in m.lessons if "Avoid bad on AAPL@1" in t]
    assert len(first) == 1
    m.learn("bad", "AAPL", "1", -0.9)
    m.distill_lessons()
    avoid = [t for t in m.lessons if "Avoid bad on AAPL@1" in t]
    assert len(avoid) == 1 and "-0.90" in avoid[0]  # fresh weight wins, stale copy dropped


def test_episodes_are_capped_and_agents_tracked() -> None:
    m = DeskMemory(max_episodes=3)
    for i in range(5):
        m.add_episode("k", {"i": i})
    assert [e["i"] for e in m.episodes] == [2, 3, 4]
    m.touch_agent("Dara", "Data", "fetched")
    m.touch_agent("Dara", "Data")
    assert m.agents["Dara"]["runs"] == 2 and m.agents["Dara"]["last_note"] == "fetched"


def test_memory_roundtrip_and_env_path(tmp_path, monkeypatch) -> None:
    path = tmp_path / "mem.json"
    monkeypatch.setenv("AOA_TRADINGVIEW_MEMORY_PATH", str(path))
    m = DeskMemory()
    m.learn("p", "BTC-USD", "240", 0.6)
    m.connectome = {"weights": [1.0]}
    m.consolidate()
    saved = m.save()
    assert saved == path and path.is_file()
    again = DeskMemory.load()
    assert again.recall("p", "BTC-USD", "240") == pytest.approx(m.recall("p", "BTC-USD", "240"))
    assert again.connectome == {"weights": [1.0]} and again.consolidations == 1
    path.write_text("{not json", encoding="utf-8")
    assert DeskMemory.load().synapses == {}
    assert DeskMemory.load(tmp_path / "missing.json").synapses == {}


# --------------------------------------------------------------------------- #
# connectome
# --------------------------------------------------------------------------- #


def _sense(**kw) -> MarketSense:
    return MarketSense(symbol="AAPL", **kw)


def test_kc_sparse_code_is_deterministic_and_sparse() -> None:
    a, b = FlyConnectome(seed=3), FlyConnectome(seed=3)
    s = _sense(trend=0.8, momentum=0.4)
    assert a.encode(s) == b.encode(s)
    assert len(a.encode(s)) == a.k_active
    assert a.encode(s) != a.encode(_sense(trend=-0.8, momentum=-0.4))
    assert FlyConnectome(seed=4).projection != a.projection


def test_bullish_sense_proposes_long_with_human_gate() -> None:
    brain = FlyConnectome()
    cmd = brain.step(_sense(trend=0.9, momentum=0.8, orderflow=0.6), preset="x")
    assert cmd.action == "enter_long"
    assert cmd.requires_human is True
    assert 0 < cmd.size_pct <= brain.max_size_pct
    assert set(cmd.channel_drive) == set(DN_CHANNELS)
    assert 0.0 <= cmd.confidence <= 1.0
    d = cmd.to_dict()
    assert d["requires_human"] and d["symbol"] == "AAPL" and "preset=x" in d["note"]


def test_bearish_sense_proposes_short_and_flat_market_holds() -> None:
    brain = FlyConnectome()
    assert brain.step(_sense(trend=-0.9, momentum=-0.8, orderflow=-0.5)).action == "enter_short"
    assert brain.step(_sense()).action == "hold"


def test_apl_inhibition_suppresses_entries_in_drawdown() -> None:
    brain = FlyConnectome()
    calm = brain.step(_sense(trend=0.9, momentum=0.8))
    stressed = brain.step(_sense(trend=0.9, momentum=0.8, volatility=1.0, drawdown=0.9))
    assert stressed.inhibition == 1.0 and stressed.size_pct == 0.0
    assert stressed.channel_drive["enter_long"] == 0.0 < calm.channel_drive["enter_long"]
    assert stressed.action == "hold"


def test_reversal_against_position_drives_exit_and_inhibition_reduces() -> None:
    brain = FlyConnectome()
    cmd = brain.step(_sense(trend=-0.9, momentum=-0.9, orderflow=-0.9, exposure=0.8))
    assert cmd.action == "exit" and cmd.size_pct == pytest.approx(brain.max_size_pct * 0.8, abs=1e-6)
    reduce = brain.step(_sense(exposure=0.8, volatility=0.9, drawdown=0.2))
    assert reduce.action in ("reduce", "exit")
    assert reduce.size_pct > 0


def test_fundamentals_veto_shrinks_long_goal() -> None:
    ok = FlyConnectome.goal_heading(_sense(trend=0.9, momentum=0.9), 0.0)
    vetoed = FlyConnectome.goal_heading(_sense(trend=0.9, momentum=0.9, fundamentals_ok=False), 0.0)
    assert 0 < vetoed < ok


def test_dopamine_reinforcement_changes_valence_in_reward_direction() -> None:
    brain = FlyConnectome(lr=0.5)
    s = _sense(trend=0.7, momentum=0.5)
    active = brain.encode(s)
    assert brain.valence(active) == 0.0
    brain.step(s)
    brain.reinforce(1.0)
    assert brain.valence(active) > 0
    assert all(brain.weights[i] > 0 for i in active)
    # eligibility decays, so an older pattern is punished less than the latest one
    other = _sense(trend=-0.7, momentum=-0.5)
    brain.step(other)
    brain.reinforce(-1.0)
    assert brain.valence(brain.encode(other)) < 0
    assert brain.dopamine_trace[-2:] == [1.0, -1.0]
    # weights are clamped
    for _ in range(50):
        brain.step(s)
        brain.reinforce(1.0)
    assert max(brain.weights) <= 3.0


def test_connectome_persistence_roundtrip() -> None:
    brain = FlyConnectome(n_kc=32, k_active=4, seed=11)
    brain.step(_sense(trend=0.5))
    brain.reinforce(0.4)
    data = json.loads(json.dumps(brain.to_json()))
    again = FlyConnectome.from_json(data)
    assert again.n_kc == 32 and again.k_active == 4 and again.seed == 11
    assert again.projection == brain.projection  # same seed → same wiring
    assert again.weights == pytest.approx(brain.weights, abs=1e-6)
    assert again.steps == 1 and again.dopamine_trace == [0.4]
    # corrupted/missing state falls back to a fresh brain
    fresh = FlyConnectome.from_json({"n_kc": 8, "weights": [1, 2]})
    assert fresh.weights == [0.0] * 8
    assert FlyConnectome.from_json(None).n_kc == 64


def test_context_lists_regions_and_human_gate() -> None:
    ctx = FlyConnectome().to_context()
    assert ctx["human_final_say"] is True
    assert set(ctx["regions"]) == set(REGIONS) and "mushroom_body" in ctx["regions"]
    assert ctx["dn_channels"] == list(DN_CHANNELS)


def test_sense_from_features_maps_each_family() -> None:
    s = sense_from_features("AAPL", {"ema_fast": 102.0, "ema_slow": 100.0, "rsi": 75.0, "z": 2.0}, close=100.0, atr=2.5)
    assert s.trend > 0 and s.momentum == pytest.approx(1.0) and s.orderflow > 0
    assert s.volatility == pytest.approx(0.5)
    st = sense_from_features("X", {"direction": -1.0, "macd_hist": 0.5}, close=100.0, atr=None)
    assert st.trend == 1.0 and st.momentum > 0 and st.volatility == 0.0
    sma = sense_from_features("X", {"sma": 90.0, "momentum_pct": 15.0}, close=100.0, atr=1.0, memory_trust=2.0, exposure=-3.0)
    assert sma.trend > 0 and sma.momentum > 0
    assert sma.memory_trust == 1.0 and sma.exposure == -1.0  # clamped
    bands = sense_from_features("X", {"upper": 110.0, "lower": 90.0}, close=105.0, atr=1.0)
    assert bands.trend > 0
    assert len(s.vector()) == 8
