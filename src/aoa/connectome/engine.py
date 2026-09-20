"""Accumulate-and-fire connectome propagation engine.

Distilled from the classic *connectome-to-robot* line of work — Busbice's
C. elegans connectome driving a GoPiGo robot, ``heyseth/worm-sim``, and the
recent fly-connectome trading experiments (``nftechie/stonkfly``): neurons
accumulate weighted input, fire when a threshold is crossed, propagate their
outgoing synaptic weights, and *motor groups* are read out as the summed
activity of designated motor neurons.

Three deliberate extensions over the classic threshold model:

* **Leak** — accumulated potential decays each step so stale stimulation dies
  out instead of eventually firing everything.
* **Refractory step** — a neuron that fires is silent on the next step,
  preventing trivial infinite loops in recurrent circuits.
* **Reward-modulated plasticity** — synapses that recently contributed to a
  fire keep an eligibility trace; :meth:`Connectome.reward` nudges traced
  weights up (positive reward) or down (negative), the same shape as the
  dopamine-gated updates used by connectome trading sims (stonkfly's
  PAM/PPL cells), in a tiny pure-Python form.

Pure Python, deterministic, no third-party dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FireEvent:
    """One neuron firing at one propagation step."""

    step: int
    neuron: str


@dataclass(frozen=True)
class MotorReadout:
    """Summed motor-group activity after a stimulation run."""

    drives: dict[str, float]
    fires: tuple[FireEvent, ...]
    steps: int

    def drive(self, group: str) -> float:
        return self.drives.get(group, 0.0)


@dataclass
class _State:
    potential: float = 0.0
    refractory: bool = False


class Connectome:
    """A weighted directed graph of neurons with threshold-fire dynamics.

    Parameters
    ----------
    synapses:
        Mapping ``pre -> {post: weight}``. Weights may be negative
        (inhibitory). Neurons appearing only as targets are created implicitly.
    motor_groups:
        Mapping ``group name -> neurons`` whose fire counts, weighted by their
        incoming drive, are summed into the group's motor output.
    threshold:
        Firing threshold (the classic Busbice model uses 30 with integer
        synapse counts as weights).
    leak:
        Fraction of accumulated potential retained per step (1.0 = no leak).
    trace_decay:
        Per-step decay of the plasticity eligibility trace.
    """

    def __init__(
        self,
        synapses: Mapping[str, Mapping[str, float]],
        *,
        motor_groups: Mapping[str, Sequence[str]] | None = None,
        threshold: float = 30.0,
        leak: float = 0.9,
        trace_decay: float = 0.8,
    ) -> None:
        if threshold <= 0:
            raise ValueError("threshold must be positive")
        if not 0.0 < leak <= 1.0:
            raise ValueError("leak must be in (0, 1]")
        self.threshold = float(threshold)
        self.leak = float(leak)
        self.trace_decay = float(trace_decay)
        self.synapses: dict[str, dict[str, float]] = {
            pre: {post: float(w) for post, w in posts.items()} for pre, posts in synapses.items()
        }
        names = set(self.synapses)
        for posts in self.synapses.values():
            names.update(posts)
        self.neurons: tuple[str, ...] = tuple(sorted(names))
        self.motor_groups: dict[str, tuple[str, ...]] = {
            g: tuple(ns) for g, ns in (motor_groups or {}).items()
        }
        for group, members in self.motor_groups.items():
            unknown = [n for n in members if n not in names]
            if unknown:
                raise ValueError(f"motor group {group!r} references unknown neurons: {unknown}")
        self._state: dict[str, _State] = {n: _State() for n in self.neurons}
        # Eligibility traces for reward-modulated plasticity: (pre, post) -> trace.
        self._trace: dict[tuple[str, str], float] = {}
        # Baseline weights: plasticity is capped relative to the original wiring.
        self._baseline: dict[tuple[str, str], float] = {
            (pre, post): w for pre, posts in self.synapses.items() for post, w in posts.items()
        }

    # ------------------------------------------------------------------ control
    def reset(self) -> None:
        """Zero all membrane potentials and refractory flags (traces kept)."""
        for st in self._state.values():
            st.potential = 0.0
            st.refractory = False

    def clear_traces(self) -> None:
        self._trace.clear()

    def potential(self, neuron: str) -> float:
        return self._state[neuron].potential

    # -------------------------------------------------------------- stimulation
    def stimulate(self, neuron: str, amount: float) -> None:
        """Add ``amount`` to a neuron's accumulated potential."""
        if neuron not in self._state:
            raise KeyError(f"unknown neuron {neuron!r}")
        self._state[neuron].potential += float(amount)

    def run(
        self,
        stimuli: Mapping[str, float] | None = None,
        *,
        steps: int = 16,
        reset: bool = True,
        sustain: bool = True,
    ) -> MotorReadout:
        """Apply ``stimuli`` and propagate for up to ``steps`` cycles.

        With ``sustain`` (the default, matching the classic connectome-robot
        loop where a sensor is stimulated every cycle while the stimulus is
        present) the stimuli are re-applied on each step; otherwise they are
        injected once up front.

        Returns the motor-group readout: for each group, the total synaptic
        drive delivered *into* its member neurons during the run (fired or
        not), plus each member fire counted at threshold strength. This gives
        a graded output even when motor neurons sit just below threshold.
        """
        if reset:
            self.reset()
        stimuli = dict(stimuli or {})
        if not sustain:
            for neuron, amount in stimuli.items():
                self.stimulate(neuron, amount)

        motor_members = {n for members in self.motor_groups.values() for n in members}
        delivered: dict[str, float] = dict.fromkeys(motor_members, 0.0)
        fires: list[FireEvent] = []

        for step in range(steps):
            if sustain:
                for neuron, amount in stimuli.items():
                    self.stimulate(neuron, amount)
            # Decay traces once per step.
            if self._trace:
                self._trace = {
                    k: v * self.trace_decay
                    for k, v in self._trace.items()
                    if v * self.trace_decay > 1e-6
                }
            fired = [
                n
                for n, st in self._state.items()
                if not st.refractory and st.potential >= self.threshold
            ]
            # Clear last step's refractory flags before marking this step's.
            for st in self._state.values():
                st.refractory = False
            if not fired:
                # Leak; stop early only when nothing can ever fire again
                # (no sustained input keeping the network alive).
                for st in self._state.values():
                    st.potential *= self.leak
                if (not sustain or not stimuli) and all(
                    st.potential < self.threshold for st in self._state.values()
                ):
                    return self._readout(delivered, fires, step + 1)
                continue
            for pre in fired:
                fires.append(FireEvent(step=step, neuron=pre))
                st = self._state[pre]
                st.potential = 0.0
                st.refractory = True
                for post, weight in self.synapses.get(pre, {}).items():
                    self._state[post].potential += weight
                    if post in delivered:
                        delivered[post] += weight
                    key = (pre, post)
                    self._trace[key] = self._trace.get(key, 0.0) + abs(weight)
            for st in self._state.values():
                st.potential *= self.leak

        return self._readout(delivered, fires, steps)

    def _readout(
        self, delivered: dict[str, float], fires: list[FireEvent], steps: int
    ) -> MotorReadout:
        fired_names = [f.neuron for f in fires]
        drives: dict[str, float] = {}
        for group, members in self.motor_groups.items():
            drive = sum(max(0.0, delivered.get(n, 0.0)) for n in members)
            drive += sum(self.threshold for n in fired_names if n in members)
            drives[group] = drive
        return MotorReadout(drives=drives, fires=tuple(fires), steps=steps)

    # -------------------------------------------------------------- plasticity
    def reward(self, signal: float, *, lr: float = 0.02, cap: float = 3.0) -> int:
        """Reward-modulated update of recently-active synapses.

        ``signal`` > 0 strengthens traced synapses toward the behaviour that
        just happened; < 0 weakens them. Each weight is kept within
        ``[w0/cap, w0*cap]`` of its **original** magnitude (``w0`` from the
        wiring this connectome was built with) so repeated rewards can never
        compound into runaway drift. Returns the number of synapses touched.
        """
        if not self._trace or signal == 0.0:
            return 0
        touched = 0
        for (pre, post), trace in self._trace.items():
            posts = self.synapses.get(pre)
            if posts is None or post not in posts:
                continue
            w = posts[post]
            w0 = self._baseline.get((pre, post), w)
            base = max(1e-9, abs(w0))
            delta = lr * signal * trace * (1.0 if w >= 0 else -1.0)
            new = w + delta
            lo, hi = (base / cap, base * cap) if w0 >= 0 else (-base * cap, -base / cap)
            posts[post] = min(hi, max(lo, new))
            touched += 1
        return touched

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "threshold": self.threshold,
            "leak": self.leak,
            "trace_decay": self.trace_decay,
            "synapses": {pre: dict(posts) for pre, posts in self.synapses.items()},
            "motor_groups": {g: list(m) for g, m in self.motor_groups.items()},
            "baseline": [[pre, post, w] for (pre, post), w in self._baseline.items()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Connectome:
        net = cls(
            data["synapses"],
            motor_groups=data.get("motor_groups", {}),
            threshold=float(data.get("threshold", 30.0)),
            leak=float(data.get("leak", 0.9)),
            trace_decay=float(data.get("trace_decay", 0.8)),
        )
        baseline = data.get("baseline")
        if baseline:
            net._baseline = {(str(pre), str(post)): float(w) for pre, post, w in baseline}
        return net

    # ------------------------------------------------------------------ inspect
    def describe(self) -> dict:
        n_syn = sum(len(p) for p in self.synapses.values())
        return {
            "neurons": len(self.neurons),
            "synapses": n_syn,
            "motor_groups": {g: len(m) for g, m in self.motor_groups.items()},
            "threshold": self.threshold,
        }


def merge_stimuli(*parts: Mapping[str, float] | Iterable[tuple[str, float]]) -> dict[str, float]:
    """Sum several stimulus dicts into one."""
    out: dict[str, float] = {}
    for part in parts:
        items = part.items() if isinstance(part, Mapping) else part
        for neuron, amount in items:
            out[neuron] = out.get(neuron, 0.0) + float(amount)
    return out
