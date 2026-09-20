"""Connectome engine + market-worm mapping tests (offline)."""

from __future__ import annotations

import pytest

from aoa.connectome.elegans import (
    SENSORY_NEURONS,
    MarketStimulus,
    MarketWorm,
    build_market_worm,
)
from aoa.connectome.engine import Connectome, merge_stimuli

UPTREND = MarketStimulus(
    momentum_short=0.8,
    momentum_long=0.6,
    vol_shock=0.05,
    drawdown=0.02,
    capitulation=0.0,
    regime_heat=0.0,
)
CRASH = MarketStimulus(
    momentum_short=-0.9,
    momentum_long=-0.5,
    vol_shock=0.9,
    drawdown=0.5,
    capitulation=0.0,
    regime_heat=0.6,
)
FLAT = MarketStimulus(
    momentum_short=0.0,
    momentum_long=0.0,
    vol_shock=0.05,
    drawdown=0.02,
    capitulation=0.0,
    regime_heat=0.0,
)


def _chain() -> Connectome:
    return Connectome(
        {"S": {"I": 20.0}, "I": {"M": 20.0}},
        motor_groups={"go": ("M",)},
        threshold=30.0,
    )


class TestEngine:
    def test_accumulate_and_fire_reaches_motor(self):
        net = _chain()
        readout = net.run({"S": 35.0}, steps=12)
        assert readout.drive("go") > 0
        assert any(f.neuron == "S" for f in readout.fires)
        assert any(f.neuron == "I" for f in readout.fires)

    def test_subthreshold_stimulus_without_sustain_dies_out(self):
        net = _chain()
        readout = net.run({"S": 10.0}, steps=12, sustain=False)
        assert readout.drive("go") == 0.0
        assert not readout.fires

    def test_sustained_subthreshold_stimulus_accumulates(self):
        net = _chain()
        readout = net.run({"S": 12.0}, steps=16)
        assert any(f.neuron == "S" for f in readout.fires)

    def test_inhibitory_weights_suppress(self):
        net = Connectome(
            {"S": {"M": 40.0}, "X": {"M": -40.0}},
            motor_groups={"go": ("M",)},
            threshold=30.0,
        )
        excited = net.run({"S": 35.0}, steps=6)
        both = net.run({"S": 35.0, "X": 35.0}, steps=6)
        assert both.drive("go") < excited.drive("go")

    def test_unknown_neuron_and_bad_group_raise(self):
        net = _chain()
        with pytest.raises(KeyError):
            net.stimulate("NOPE", 10.0)
        with pytest.raises(ValueError):
            Connectome({"A": {"B": 1.0}}, motor_groups={"go": ("MISSING",)})

    def test_reward_moves_traced_weights_within_cap(self):
        net = _chain()
        w0 = net.synapses["S"]["I"]
        net.run({"S": 35.0}, steps=6)
        touched = net.reward(1.0, lr=0.5)
        assert touched > 0
        assert net.synapses["S"]["I"] > w0
        for _ in range(50):
            net.run({"S": 35.0}, steps=6)
            net.reward(1.0, lr=1.0)
        assert net.synapses["S"]["I"] <= w0 * 3.0 + 1e-9  # cap holds

    def test_negative_reward_weakens(self):
        net = _chain()
        w0 = net.synapses["S"]["I"]
        net.run({"S": 35.0}, steps=6)
        net.reward(-1.0, lr=0.5)
        assert net.synapses["S"]["I"] < w0

    def test_round_trip_serialization(self):
        net = build_market_worm()
        clone = Connectome.from_dict(net.to_dict())
        assert clone.describe() == net.describe()
        assert clone.synapses == net.synapses

    def test_merge_stimuli_sums(self):
        merged = merge_stimuli({"A": 1.0, "B": 2.0}, {"A": 3.0})
        assert merged == {"A": 4.0, "B": 2.0}


class TestMarketWorm:
    def test_uptrend_buys_and_crash_sells(self):
        worm = MarketWorm()
        assert worm.decide(UPTREND).action == "buy"
        assert worm.decide(CRASH).action == "sell"

    def test_flat_market_holds(self):
        worm = MarketWorm()
        decision = worm.decide(FLAT)
        assert decision.action == "hold"
        assert decision.conviction == 0.0

    def test_decisions_are_deterministic(self):
        worm = MarketWorm()
        first = worm.decide(UPTREND)
        second = worm.decide(UPTREND)
        assert first == second

    def test_stimuli_only_touch_sensory_neurons(self):
        worm = MarketWorm()
        for stim in (UPTREND, CRASH, FLAT):
            for neuron in worm.stimuli_for(stim):
                assert neuron in SENSORY_NEURONS

    def test_reinforce_shifts_behaviour(self):
        worm = MarketWorm()
        base = worm.decide(UPTREND).conviction
        for _ in range(30):
            worm.decide(UPTREND)
            worm.reinforce(1.0, lr=0.2)
        assert worm.decide(UPTREND).conviction >= base
