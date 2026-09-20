"""Fly-brain connectome mapped onto trade decision → motor output.

The adult *Drosophila* connectome (FlyWire / hemibrain / MANC / BANC) shows a
compact sensorimotor architecture: sensory neuropils feed sparse **Kenyon
cells** in the mushroom body; **dopaminergic neurons (DANs)** write valence
into KC→**MBON** synapses (reinforcement learning); MBONs and the **central
complex** (head-direction / goal-direction, PFL neurons) converge on a small
set of **descending neurons (DNs)**; DNs drive **motor neurons** in the
ventral nerve cord, while **ascending neurons (ANs)** copy motor state back up.

We use the *same wiring diagram* as the control loop of the desk:

====================  =====================================================
Fly circuit           Trading role
====================  =====================================================
optic / antennal lobe ``MarketSense`` — normalised bar features
Kenyon cells          sparse k-winners code of the sense vector (random
                      projection, seeded → reproducible)
MBONs + DANs          valence weights per KC; ``reinforce(reward)`` is the
                      dopamine signal (three-factor rule: eligibility × DA)
APL (GABAergic)       global inhibition — volatility / drawdown risk-off gain
central complex       goal heading (desired exposure) vs current heading
                      (actual exposure) → steering error
descending neurons    5 channels: enter_long · enter_short · hold · reduce ·
                      exit; lateral inhibition → winner-take-all
motor neurons (VNC)   :class:`MotorCommand` proposal — **never** an order
ascending neurons     fills / PnL feed back into ``reinforce``
====================  =====================================================

The human is the final gate: every :class:`MotorCommand` has
``requires_human=True`` and the desk only records proposals. The existing
deterministic risk guards (``aoa.risk.guards``) sit downstream and are never
touched by this module.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

DN_CHANNELS: tuple[str, ...] = ("enter_long", "enter_short", "hold", "reduce", "exit")

REGIONS: dict[str, dict[str, str]] = {
    "optic_lobe": {"biology": "visual sensory neuropil", "role": "price/volume/volatility sensing"},
    "antennal_lobe": {"biology": "olfactory glomeruli", "role": "order-flow & regime 'odours'"},
    "kenyon_cells": {"biology": "~2,600 KCs/hemisphere sparse coding", "role": "sparse feature expansion"},
    "mushroom_body": {"biology": "KC→MBON synapses, DAN modulated", "role": "valence memory (preset trust)"},
    "apl": {"biology": "GABAergic giant interneuron", "role": "global risk-off inhibition"},
    "central_complex": {"biology": "head-direction / goal (PFL)", "role": "exposure steering error"},
    "descending_neurons": {"biology": "~1,300 DNs brain→VNC", "role": "discrete action channels"},
    "motor_neurons": {"biology": "VNC leg/wing motor pools", "role": "motor command proposal (human-gated)"},
    "ascending_neurons": {"biology": "VNC→brain efference copy", "role": "fill / PnL feedback"},
}


@dataclass(frozen=True)
class MarketSense:
    """Normalised sensory vector for one symbol at one moment."""

    symbol: str
    trend: float = 0.0  # -1..1 (e.g. EMA fast vs slow, sign & magnitude)
    momentum: float = 0.0  # -1..1 (RSI centred / momentum z)
    orderflow: float = 0.0  # -1..1 (cum-delta z-score squashed)
    volatility: float = 0.0  # 0..1 (ATR / price relative to its typical level)
    drawdown: float = 0.0  # 0..1 (current account drawdown fraction)
    memory_trust: float = 0.0  # -1..1 (DeskMemory recall for the active preset)
    exposure: float = 0.0  # -1..1 current signed exposure fraction
    fundamentals_ok: bool = True

    def vector(self) -> list[float]:
        return [
            self.trend,
            self.momentum,
            self.orderflow,
            self.volatility,
            self.drawdown,
            self.memory_trust,
            self.exposure,
            1.0 if self.fundamentals_ok else -1.0,
        ]


@dataclass
class MotorCommand:
    symbol: str
    action: str
    size_pct: float
    confidence: float
    channel_drive: dict[str, float]
    steering_error: float
    valence: float
    inhibition: float
    active_kcs: list[int]
    requires_human: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "size_pct": round(self.size_pct, 3),
            "confidence": round(self.confidence, 4),
            "channel_drive": {k: round(v, 4) for k, v in self.channel_drive.items()},
            "steering_error": round(self.steering_error, 4),
            "valence": round(self.valence, 4),
            "inhibition": round(self.inhibition, 4),
            "active_kcs": list(self.active_kcs),
            "requires_human": self.requires_human,
            "note": self.note,
        }


@dataclass
class FlyConnectome:
    """Deterministic, dependency-free sensorimotor loop."""

    n_kc: int = 64
    k_active: int = 8
    seed: int = 7
    lr: float = 0.15
    eligibility_decay: float = 0.6
    max_size_pct: float = 15.0
    weights: list[float] = field(default_factory=list)  # KC → MBON valence (approach>0, avoid<0)
    eligibility: list[float] = field(default_factory=list)
    projection: list[list[float]] = field(default_factory=list)
    dopamine_trace: list[float] = field(default_factory=list)
    steps: int = 0

    def __post_init__(self) -> None:
        dim = len(MarketSense(symbol="_").vector())
        rng = random.Random(self.seed)
        if not self.projection:
            self.projection = [[rng.gauss(0.0, 1.0) for _ in range(dim)] for _ in range(self.n_kc)]
        if not self.weights:
            self.weights = [0.0] * self.n_kc
        if not self.eligibility:
            self.eligibility = [0.0] * self.n_kc

    # ------------------------------------------------------------- sensing
    def encode(self, sense: MarketSense) -> list[int]:
        """Kenyon-cell sparse code: top-``k_active`` projections (APL-normalised)."""
        vec = sense.vector()
        acts = [sum(w * x for w, x in zip(row, vec, strict=True)) for row in self.projection]
        order = sorted(range(self.n_kc), key=lambda i: acts[i], reverse=True)
        return sorted(order[: self.k_active])

    def valence(self, active: list[int]) -> float:
        if not active:
            return 0.0
        return math.tanh(sum(self.weights[i] for i in active) / math.sqrt(len(active)))

    # ------------------------------------------------------------ steering
    @staticmethod
    def goal_heading(sense: MarketSense, valence: float) -> float:
        """Central-complex goal: desired signed exposure in [-1, 1]."""
        evidence = 0.45 * sense.trend + 0.25 * sense.momentum + 0.30 * sense.orderflow
        goal = math.tanh(1.5 * evidence + 0.8 * valence + 0.5 * sense.memory_trust)
        if not sense.fundamentals_ok and goal > 0:
            goal *= 0.25
        return goal

    @staticmethod
    def inhibition(sense: MarketSense) -> float:
        """APL-like global inhibition: 0 (free) … 1 (fully suppressed)."""
        return max(0.0, min(1.0, 0.6 * sense.volatility + 0.8 * sense.drawdown))

    def descend(self, sense: MarketSense, goal: float, inhib: float, valence: float) -> dict[str, float]:
        """Descending-neuron drives before lateral inhibition."""
        err = goal - sense.exposure
        gain = 1.0 - inhib
        # Entry DNs are damped while any position is open so a reversal exits first
        # (opposing motor programs are mutually inhibitory) instead of flipping.
        flat = abs(sense.exposure) <= 0.05
        entry_gate = 1.0 if flat else 0.3
        drive = {
            "enter_long": max(0.0, err) * gain * entry_gate,
            "enter_short": max(0.0, -err) * gain * entry_gate,
            "hold": 0.35 + 0.4 * (1.0 - abs(err)) + 0.2 * max(valence, 0.0) * (1.0 if abs(sense.exposure) > 0.05 else 0.0),
            "reduce": abs(sense.exposure) * (0.9 * inhib + max(0.0, -valence) * 0.5),
            "exit": abs(sense.exposure) * (inhib**2 + (1.0 if (sense.exposure > 0 and goal < -0.3) or (sense.exposure < 0 and goal > 0.3) else 0.0)),
        }
        if flat:
            drive["reduce"] = 0.0
            drive["exit"] = 0.0
        return drive

    @staticmethod
    def winner_take_all(drive: dict[str, float]) -> tuple[str, float]:
        """Lateral inhibition: the strongest channel wins; confidence = margin."""
        ranked = sorted(drive.items(), key=lambda kv: kv[1], reverse=True)
        best, second = ranked[0], ranked[1]
        total = sum(max(v, 0.0) for v in drive.values()) or 1.0
        confidence = max(0.0, min(1.0, (best[1] - second[1]) / total + best[1] / (total + 1e-9) * 0.5))
        return best[0], confidence

    # ------------------------------------------------------------- the loop
    def step(self, sense: MarketSense, *, preset: str = "") -> MotorCommand:
        active = self.encode(sense)
        for i in range(self.n_kc):
            self.eligibility[i] *= self.eligibility_decay
        for i in active:
            self.eligibility[i] = 1.0
        val = self.valence(active)
        inhib = self.inhibition(sense)
        goal = self.goal_heading(sense, val)
        drive = self.descend(sense, goal, inhib, val)
        action, conf = self.winner_take_all(drive)
        err = goal - sense.exposure
        size = 0.0
        if action in ("enter_long", "enter_short"):
            size = self.max_size_pct * min(1.0, abs(err)) * (1.0 - inhib) * (0.5 + 0.5 * conf)
        elif action == "reduce":
            size = self.max_size_pct * 0.5 * abs(sense.exposure)
        elif action == "exit":
            size = self.max_size_pct * abs(sense.exposure)
        self.steps += 1
        note = f"preset={preset or 'n/a'} goal={goal:+.2f} exposure={sense.exposure:+.2f} inhib={inhib:.2f}"
        return MotorCommand(
            symbol=sense.symbol,
            action=action,
            size_pct=round(size, 3),
            confidence=conf,
            channel_drive=drive,
            steering_error=err,
            valence=val,
            inhibition=inhib,
            active_kcs=active,
            note=note,
        )

    def reinforce(self, reward: float) -> float:
        """Dopamine: three-factor update on eligible KC→MBON synapses.

        Positive reward strengthens approach valence of the recently active
        KCs; negative reward (loss, veto) pushes them toward avoidance.
        """
        r = max(-1.0, min(1.0, float(reward)))
        for i in range(self.n_kc):
            e = self.eligibility[i]
            if e > 1e-6:
                self.weights[i] = max(-3.0, min(3.0, self.weights[i] + self.lr * r * e))
        self.dopamine_trace.append(round(r, 4))
        if len(self.dopamine_trace) > 500:
            self.dopamine_trace = self.dopamine_trace[-500:]
        return r

    # ----------------------------------------------------------- persistence
    def to_json(self) -> dict[str, Any]:
        return {
            "n_kc": self.n_kc,
            "k_active": self.k_active,
            "seed": self.seed,
            "lr": self.lr,
            "weights": [round(w, 6) for w in self.weights],
            "eligibility": [round(e, 6) for e in self.eligibility],
            "dopamine_trace": self.dopamine_trace[-100:],
            "steps": self.steps,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> FlyConnectome:
        data = data or {}
        obj = cls(
            n_kc=int(data.get("n_kc", 64) or 64),
            k_active=int(data.get("k_active", 8) or 8),
            seed=int(data.get("seed", 7) or 7),
            lr=float(data.get("lr", 0.15) or 0.15),
        )
        w = data.get("weights")
        if isinstance(w, list) and len(w) == obj.n_kc:
            obj.weights = [float(x) for x in w]
        e = data.get("eligibility")
        if isinstance(e, list) and len(e) == obj.n_kc:
            obj.eligibility = [float(x) for x in e]
        obj.dopamine_trace = [float(x) for x in data.get("dopamine_trace") or []]
        obj.steps = int(data.get("steps", 0) or 0)
        return obj

    def to_context(self) -> dict[str, Any]:
        strongest = sorted(range(self.n_kc), key=lambda i: abs(self.weights[i]), reverse=True)[:5]
        return {
            "regions": REGIONS,
            "dn_channels": list(DN_CHANNELS),
            "n_kc": self.n_kc,
            "k_active": self.k_active,
            "steps": self.steps,
            "mean_valence_weight": round(sum(self.weights) / self.n_kc, 4) if self.n_kc else 0.0,
            "strongest_kcs": [{"kc": i, "weight": round(self.weights[i], 4)} for i in strongest],
            "recent_dopamine": self.dopamine_trace[-10:],
            "human_final_say": True,
        }


def sense_from_features(
    symbol: str,
    features: dict[str, float],
    *,
    close: float,
    atr: float | None,
    memory_trust: float = 0.0,
    exposure: float = 0.0,
    drawdown: float = 0.0,
    fundamentals_ok: bool = True,
) -> MarketSense:
    """Translate strategy features (see ``rules.Signal.features``) into a sense vector."""
    trend = 0.0
    if "ema_fast" in features and "ema_slow" in features and features["ema_slow"]:
        trend = math.tanh((features["ema_fast"] / features["ema_slow"] - 1.0) * 50.0)
    elif "direction" in features:
        trend = -float(features["direction"])  # supertrend: -1 = up
    elif "sma" in features and features["sma"]:
        trend = math.tanh((close / features["sma"] - 1.0) * 10.0)
    elif "upper" in features and "lower" in features and features["upper"] != features["lower"]:
        mid = (features["upper"] + features["lower"]) / 2.0
        trend = math.tanh((close - mid) / (features["upper"] - features["lower"]) * 2.0)
    momentum = 0.0
    if "rsi" in features:
        momentum = max(-1.0, min(1.0, (features["rsi"] - 50.0) / 25.0))
    elif "momentum_pct" in features:
        momentum = math.tanh(features["momentum_pct"] / 20.0)
    elif "macd_hist" in features and close:
        momentum = math.tanh(features["macd_hist"] / close * 200.0)
    orderflow = math.tanh(features.get("z", 0.0) / 2.0) if "z" in features else 0.0
    vol = 0.0
    if atr and close:
        vol = max(0.0, min(1.0, (atr / close) / 0.05))
    return MarketSense(
        symbol=symbol,
        trend=trend,
        momentum=momentum,
        orderflow=orderflow,
        volatility=vol,
        drawdown=max(0.0, min(1.0, drawdown)),
        memory_trust=max(-1.0, min(1.0, memory_trust)),
        exposure=max(-1.0, min(1.0, exposure)),
        fundamentals_ok=fundamentals_ok,
    )
