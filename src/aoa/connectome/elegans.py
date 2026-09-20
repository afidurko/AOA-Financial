"""Curated C. elegans sub-connectome mapped to market motor outputs.

The worm's best-understood circuits are chemotaxis (find food) and the touch
reflex (escape threat). Both funnel through the command interneurons:

* **Forward** — AVB / PVC drive the B-class motor neurons (locomote toward
  food).
* **Backward** — AVA / AVD / AVE drive the A-class motor neurons (reverse away
  from an anterior touch).

The market mapping keeps the same wiring and reads the two locomotion drives
as *risk appetite*:

* AWA/AWC (food)       — positive momentum: an uptrend "smells like food"
* ASE (salt gradient)  — longer-horizon trend confirmation
* ASH (nociception)    — volatility shock: acrid chemical ≈ violent tape
* ALM/AVM (nose touch) — sharp drawdown from recent peak: bump ≈ crash
* PLM (tail touch)     — capitulation bounce: a tap from behind pushes forward
* AFD (thermotaxis)    — regime deviation from learned comfort temperature

Forward drive maps to *long exposure*, reversal maps to *exit / stand aside*.
The synapse weights are distilled connection counts from the published
hermaphrodite wiring (White et al. 1986; Varshney et al. 2011) — collapsed
left/right pairs, restricted to these circuits, and rounded. They are a
research approximation of the biology, not a full 302-neuron reconstruction
(see ``openworm`` / Busbice's connectome for that).
"""

from __future__ import annotations

from dataclasses import dataclass

from aoa.connectome.engine import Connectome, MotorReadout

# --- curated wiring ---------------------------------------------------------
# pre -> {post: weight}. Positive = excitatory, negative = inhibitory.
# Collapsed L/R pairs; weights ≈ synapse counts in the published connectome,
# scaled so a strongly-stimulated sensory layer can drive motors in a few
# steps with threshold 30.
_WIRING: dict[str, dict[str, float]] = {
    # Chemosensory (food / attraction) → amphid interneurons.
    "AWA": {"AIA": 12.0, "AIZ": 10.0, "AIY": 6.0},
    "AWC": {"AIY": 14.0, "AIA": 8.0, "AIB": 6.0},
    "ASE": {"AIY": 13.0, "AIA": 9.0, "AIB": 5.0},
    # Nociceptive (harsh stimuli) → backward command.
    "ASH": {"AVA": 12.0, "AVD": 10.0, "AVB": -4.0, "AIB": 6.0},
    # Gentle-touch mechanosensors.
    "ALM": {"AVD": 12.0, "AVA": 6.0, "PVC": -3.0},
    "AVM": {"AVD": 10.0, "AVA": 5.0, "AVB": -3.0},
    "PLM": {"PVC": 12.0, "AVB": 5.0, "AVD": -4.0},
    # Thermosensory → AIY (comfort) / AIZ (deviation).
    "AFD": {"AIY": 15.0, "AIZ": -5.0},
    # First-layer interneurons → command layer.
    "AIA": {"AIY": 8.0, "AIB": -5.0},
    "AIY": {"AIZ": 9.0, "AVB": 11.0, "AIB": -6.0},
    "AIZ": {"AVB": 10.0, "AIB": 5.0, "AVA": 3.0},
    "AIB": {"AVA": 9.0, "AVB": -6.0, "AVE": 5.0},
    # Command interneurons → motor classes.
    "AVB": {"DB": 16.0, "VB": 14.0, "AVA": -5.0},
    "PVC": {"DB": 12.0, "VB": 10.0, "AVA": -4.0},
    "AVA": {"DA": 16.0, "VA": 14.0, "AVB": -5.0},
    "AVD": {"DA": 10.0, "VA": 8.0, "AVA": 6.0},
    "AVE": {"DA": 9.0, "VA": 7.0},
    # Motor cross-inhibition (reciprocal gait suppression).
    "DB": {"DA": -3.0},
    "DA": {"DB": -3.0},
}

_MOTOR_GROUPS = {
    # B-class = forward locomotion = risk-on; A-class = reversal = risk-off.
    "forward": ("DB", "VB"),
    "backward": ("DA", "VA"),
}

SENSORY_NEURONS = ("AWA", "AWC", "ASE", "ASH", "ALM", "AVM", "PLM", "AFD")


def build_market_worm(*, threshold: float = 30.0, leak: float = 0.9) -> Connectome:
    """A fresh curated worm connectome with forward/backward motor readout."""
    return Connectome(
        {pre: dict(posts) for pre, posts in _WIRING.items()},
        motor_groups=_MOTOR_GROUPS,
        threshold=threshold,
        leak=leak,
    )


# --- market sensory mapping --------------------------------------------------


@dataclass(frozen=True)
class MarketStimulus:
    """Normalized market features for one bar, each roughly in [-1, 1] / [0, 1]."""

    momentum_short: float  # ~5-bar return, tanh-normalized
    momentum_long: float  # ~20-bar return, tanh-normalized
    vol_shock: float  # [0, 1] — realized vol vs its own recent baseline
    drawdown: float  # [0, 1] — fraction below the trailing peak
    capitulation: float  # [0, 1] — bounce off a deep low
    regime_heat: float  # [-1, 1] — deviation from learned "comfort" regime


@dataclass(frozen=True)
class MotorDecision:
    """The worm's motor output translated into a trading intent."""

    action: str  # "buy" | "sell" | "hold"
    conviction: float  # [0, 1]
    forward_drive: float
    reverse_drive: float
    fires: int

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "conviction": round(self.conviction, 4),
            "forward_drive": round(self.forward_drive, 2),
            "reverse_drive": round(self.reverse_drive, 2),
            "fires": self.fires,
        }


class MarketWorm:
    """Feed market features to the worm; read locomotion as trading intent.

    ``gain`` scales stimulation strength; ``deadband`` is the minimum
    normalized net drive before the worm commits to a direction.
    """

    def __init__(
        self,
        connectome: Connectome | None = None,
        *,
        gain: float = 40.0,
        deadband: float = 0.08,
    ) -> None:
        self.connectome = connectome or build_market_worm()
        self.gain = float(gain)
        self.deadband = float(deadband)

    def stimuli_for(self, s: MarketStimulus) -> dict[str, float]:
        g = self.gain
        stim: dict[str, float] = {}
        if s.momentum_short > 0:
            stim["AWA"] = g * s.momentum_short
            stim["AWC"] = 0.8 * g * s.momentum_short
        if s.momentum_long > 0:
            stim["ASE"] = g * s.momentum_long
        # Threat pathway: vol shocks and drawdowns bump the nose.
        if s.vol_shock > 0:
            stim["ASH"] = g * s.vol_shock
        if s.drawdown > 0:
            stim["ALM"] = g * s.drawdown
            stim["AVM"] = 0.6 * g * s.drawdown
        # Bear-market rallies also *smell* wrong: negative momentum tickles ASH.
        neg = max(0.0, -s.momentum_short)
        if neg > 0:
            stim["ASH"] = stim.get("ASH", 0.0) + 0.7 * g * neg
        if s.capitulation > 0:
            stim["PLM"] = g * s.capitulation
        if s.regime_heat != 0:
            stim["AFD"] = g * max(0.0, 1.0 - abs(s.regime_heat))
        return stim

    def decide(self, s: MarketStimulus) -> MotorDecision:
        readout: MotorReadout = self.connectome.run(self.stimuli_for(s), steps=24)
        fwd = readout.drive("forward")
        rev = readout.drive("backward")
        total = fwd + rev
        if total <= 0:
            return MotorDecision("hold", 0.0, fwd, rev, len(readout.fires))
        net = (fwd - rev) / total  # [-1, 1]
        conviction = min(1.0, abs(net) * min(1.0, total / (4 * self.connectome.threshold)))
        if net > self.deadband:
            action = "buy"
        elif net < -self.deadband:
            action = "sell"
        else:
            action, conviction = "hold", 0.0
        return MotorDecision(action, conviction, fwd, rev, len(readout.fires))

    def reinforce(self, realized_return: float, *, lr: float = 0.01) -> int:
        """Dopamine-style update: reward the circuits active on the last decision."""
        return self.connectome.reward(realized_return, lr=lr)
