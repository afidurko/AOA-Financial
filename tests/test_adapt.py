"""Tests for the low-rank adaptation toolkit and its swarm integration."""

from __future__ import annotations

import pytest

from aoa.adapt.lowrank import LowRankAdapter
from aoa.adapt.signal_adapter import SignalAdapter
from aoa.agents.base import Direction, Signal


# ----------------------------------------------------------------- low-rank core
def test_adapter_starts_as_noop():
    # A is initialized to zeros => ΔW is exactly 0 at the start (the LoRA property).
    adapter = LowRankAdapter(in_features=5, out_features=2, rank=3)
    x = [0.4, -1.0, 0.2, 1.0, 0.5]
    assert adapter.delta(x) == [0.0, 0.0]
    assert adapter.apply(x, [0.3, 0.7]) == [0.3, 0.7]
    assert adapter.effective_weight() == [[0.0] * 5, [0.0] * 5]


def test_sgd_step_reduces_squared_error():
    adapter = LowRankAdapter(in_features=4, out_features=1, rank=2, seed=1)
    x = [1.0, 0.5, -0.5, 1.0]
    target = 0.8

    def loss() -> float:
        pred = adapter.delta(x)[0]
        return 0.5 * (pred - target) ** 2

    before = loss()
    for _ in range(200):
        pred = adapter.delta(x)[0]
        adapter.sgd_step(x, [pred - target], lr=0.1)
    after = loss()
    assert after < before
    assert adapter.delta(x)[0] == pytest.approx(target, abs=0.05)


def test_lowrank_roundtrip(tmp_path):
    adapter = LowRankAdapter(in_features=3, out_features=2, rank=2, seed=7)
    x = [0.1, 0.2, 0.3]
    for _ in range(10):
        adapter.sgd_step(x, [0.5, -0.5], lr=0.05)
    path = tmp_path / "a.json"
    adapter.save(path)
    restored = LowRankAdapter.load(path)
    assert restored.delta(x) == pytest.approx(adapter.delta(x))


def test_rank_must_be_positive():
    with pytest.raises(ValueError):
        LowRankAdapter(in_features=3, out_features=1, rank=0)


# -------------------------------------------------------------- signal adapter
def _sig(direction=Direction.BULLISH, conviction=0.6, source="technical"):
    return Signal(symbol="AAPL", source=source, direction=direction,
                  conviction=conviction, rationale="x", horizon="swing")


def test_signal_adapter_initial_passthrough():
    sa = SignalAdapter()
    out = sa.adapt_signal(_sig(conviction=0.6))
    assert out.conviction == pytest.approx(0.6)
    assert "adapted" in out.tags


def test_neutral_signal_untouched():
    sa = SignalAdapter()
    sig = _sig(direction=Direction.NEUTRAL, conviction=0.4)
    out = sa.adapt_signal(sig)
    assert out is sig  # nothing to size, returned unchanged
    # And neutral outcomes teach nothing.
    assert sa.record_outcome(agent="technical", direction="neutral",
                             conviction=0.4, realized_return=0.1) == 0.0


def test_learns_to_raise_conviction_when_consistently_right():
    sa = SignalAdapter(lr=0.1)
    # A bullish technical call that keeps being followed by a big up move.
    for _ in range(150):
        sa.record_outcome(agent="technical", direction="bullish",
                          conviction=0.5, realized_return=0.10)
    adj, _ = sa.adjusted_conviction(agent="technical", direction="bullish", conviction=0.5)
    assert adj > 0.5
    assert sa.updates == 150


def test_learns_to_cut_conviction_when_consistently_wrong():
    sa = SignalAdapter(lr=0.1)
    # A bullish call repeatedly followed by a drop => should be deflated.
    for _ in range(150):
        sa.record_outcome(agent="technical", direction="bullish",
                          conviction=0.7, realized_return=-0.10)
    adj, _ = sa.adjusted_conviction(agent="technical", direction="bullish", conviction=0.7)
    assert adj < 0.7


def test_signal_adapter_roundtrip(tmp_path):
    sa = SignalAdapter(lr=0.1)
    for _ in range(20):
        sa.record_outcome(agent="fundamental", direction="bearish",
                          conviction=0.6, realized_return=-0.08)
    path = tmp_path / "sa.json"
    sa.save(path)
    restored = SignalAdapter.load(path)
    assert restored.updates == sa.updates
    a = restored.adjusted_conviction(agent="fundamental", direction="bearish", conviction=0.6)
    b = sa.adjusted_conviction(agent="fundamental", direction="bearish", conviction=0.6)
    assert a == pytest.approx(b)


def test_load_or_new_falls_back(tmp_path):
    missing = tmp_path / "nope.json"
    sa = SignalAdapter.load_or_new(missing, rank=2)
    assert isinstance(sa, SignalAdapter)
    assert sa.updates == 0


# ---------------------------------------------------------- swarm integration
def test_orchestrator_adapts_and_learns(fake_broker, fake_llm, tmp_path):
    from aoa.config import Config, RiskLimits
    from aoa.journal.store import Journal
    from aoa.swarm.orchestrator import Orchestrator

    cfg = Config(anthropic_api_key="x", alpaca_key_id="x", alpaca_secret_key="x",
                 universe=("AAPL",), dry_run=True,
                 trading_agents_enabled=False,
                 risk=RiskLimits(max_orders_per_cycle=5))
    journal = Journal(tmp_path / "j.jsonl")
    adapter = SignalAdapter(lr=0.1)
    orch = Orchestrator(cfg, fake_broker, fake_llm, journal, signal_adapter=adapter)

    # Cycle 1: no prior to learn from, but raw agent signals are recalibrated (tagged).
    r1 = orch.run_cycle()
    agent_sigs = [
        s
        for s in r1.blackboard.signals_for("AAPL")
        if s.source in ("technical", "fundamental")
    ]
    assert agent_sigs and all("adapted" in s.tags for s in agent_sigs)
    assert adapter.updates == 0  # nothing to learn from yet

    # Cycle 2: prior cycle's signals are scored against the realized move.
    orch.run_cycle()
    assert adapter.updates == 2  # technical + fundamental scored

    events = {e["event"] for e in journal.tail(100)}
    assert "adapt.applied" in events


def test_orchestrator_without_adapter_unchanged(fake_broker, fake_llm, tmp_path):
    from aoa.config import Config, RiskLimits
    from aoa.journal.store import Journal
    from aoa.swarm.orchestrator import Orchestrator

    cfg = Config(anthropic_api_key="x", alpaca_key_id="x", alpaca_secret_key="x",
                 universe=("AAPL",), dry_run=True,
                 trading_agents_enabled=False,
                 risk=RiskLimits(max_orders_per_cycle=5))
    orch = Orchestrator(cfg, fake_broker, fake_llm, Journal(tmp_path / "j.jsonl"))
    r = orch.run_cycle()
    agent_sigs = [
        s
        for s in r.blackboard.signals_for("AAPL")
        if s.source in ("technical", "fundamental")
    ]
    assert agent_sigs and all("adapted" not in s.tags for s in agent_sigs)


# ------------------------------------------------------------------ torch LoRA
def test_torch_lora_optional():
    torch = pytest.importorskip("torch")
    from torch import nn

    from aoa.adapt.torch_lora import (
        LoRALinear,
        load_lora_adapter,
        mark_only_lora_as_trainable,
        save_lora_adapter,
    )

    base = nn.Linear(16, 8)
    layer = LoRALinear.from_linear(base, rank=4, alpha=8)
    x = torch.randn(3, 16)

    # lora_B starts at zero => the adapter is a no-op matching the base linear.
    assert torch.allclose(layer(x), base(x), atol=1e-6)

    # Only LoRA params are trainable.
    mark_only_lora_as_trainable(layer)
    trainable = {n for n, p in layer.named_parameters() if p.requires_grad}
    assert trainable == {"lora_A", "lora_B"}

    # Give the adapter a non-trivial delta, then check merge/unmerge equivalence.
    with torch.no_grad():
        layer.lora_B.add_(0.1)
    y = layer(x)
    layer.merge()
    assert torch.allclose(layer(x), y, atol=1e-5)
    layer.unmerge()
    assert torch.allclose(layer(x), y, atol=1e-5)

    # Adapter checkpoint contains only the tiny LoRA tensors.
    import os

    path = os.path.join(os.path.dirname(__file__), "_tmp_adapter.pt")
    try:
        save_lora_adapter(layer, path)
        fresh = LoRALinear.from_linear(base, rank=4, alpha=8)
        load_lora_adapter(fresh, path)
        assert torch.allclose(fresh.lora_B, layer.lora_B)
    finally:
        if os.path.exists(path):
            os.remove(path)
