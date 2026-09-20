"""Pure-Python deep learning cores for the crypto trader swarm.

Two models, both dependency-free, seeded, and JSON-persistable:

* :class:`DeepMLP` — a genuinely deep feed-forward network (arbitrary hidden
  layers, tanh activations, full backpropagation, SGD with momentum). The
  workhorse behind the deep predictive traders, in the spirit of the account's
  ``deepstock`` / ``Stock-Price-Prediction`` experiments but small enough to
  train online, day by day, on any machine the swarm runs on.

* :class:`GatedReservoir` — a recurrent state-space model with **input-
  selective gating**: the state update strength is itself a learned function
  of the input, the central trick distilled from the account's GHOST fork
  (sentiment-*gated* Mamba) and the Mamba-vs-LSTM comparison repo. The
  recurrent weights form a fixed, spectral-radius-scaled reservoir (echo-state
  style, so the recurrence is stable without backprop-through-time); the
  selective gate and the readout are trained online by SGD.

Both expose ``predict(x)``, ``train_step(x, target)``, ``to_dict``/``from_dict``.
Inputs are small feature vectors (≈12–32 dims), so plain Python lists are fast
enough for decades of daily bars.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def _rand_matrix(rng: random.Random, rows: int, cols: int, std: float) -> list[list[float]]:
    return [[rng.gauss(0.0, std) for _ in range(cols)] for _ in range(rows)]


def _matvec(m: Sequence[Sequence[float]], v: Sequence[float]) -> list[float]:
    return [sum(w * x for w, x in zip(row, v, strict=True)) for row in m]


def _tanh_vec(v: Sequence[float]) -> list[float]:
    return [math.tanh(x) for x in v]


class DeepMLP:
    """A deep tanh MLP trained by full backpropagation (SGD + momentum).

    ``layers`` gives every layer width, e.g. ``[12, 16, 8, 1]`` builds two
    hidden layers. He-style initialization scaled for tanh; the final layer is
    linear so the network can regress signed return targets.
    """

    def __init__(self, layers: Sequence[int], *, seed: int = 0, momentum: float = 0.9) -> None:
        if len(layers) < 2:
            raise ValueError("need at least input and output layer sizes")
        if any(n <= 0 for n in layers):
            raise ValueError("layer sizes must be positive")
        self.layers = list(layers)
        self.momentum = float(momentum)
        rng = random.Random(seed)
        self.weights: list[list[list[float]]] = []
        self.biases: list[list[float]] = []
        for fan_in, fan_out in zip(layers, layers[1:], strict=False):
            std = math.sqrt(1.0 / fan_in)
            self.weights.append(_rand_matrix(rng, fan_out, fan_in, std))
            self.biases.append([0.0] * fan_out)
        self._vel_w = [[[0.0] * len(row) for row in w] for w in self.weights]
        self._vel_b = [[0.0] * len(b) for b in self.biases]

    @property
    def n_params(self) -> int:
        return sum(len(r) for w in self.weights for r in w) + sum(len(b) for b in self.biases)

    # ------------------------------------------------------------------ forward
    def _forward(self, x: Sequence[float]) -> list[list[float]]:
        """Return activations per layer (input first, linear output last)."""
        if len(x) != self.layers[0]:
            raise ValueError(f"expected input of length {self.layers[0]}, got {len(x)}")
        acts: list[list[float]] = [list(x)]
        h = list(x)
        last = len(self.weights) - 1
        for i, (w, b) in enumerate(zip(self.weights, self.biases, strict=True)):
            z = [zi + bi for zi, bi in zip(_matvec(w, h), b, strict=True)]
            h = z if i == last else _tanh_vec(z)
            acts.append(h)
        return acts

    def predict(self, x: Sequence[float]) -> float:
        return self._forward(x)[-1][0]

    # ----------------------------------------------------------------- training
    def train_step(
        self, x: Sequence[float], target: float, *, lr: float = 0.01, weight_decay: float = 1e-5
    ) -> float:
        """One SGD+momentum step on ½(pred − target)²; returns the error."""
        acts = self._forward(x)
        pred = acts[-1][0]
        err = pred - target

        # Backprop: delta for the linear output layer is just the error.
        delta = [err]
        for i in range(len(self.weights) - 1, -1, -1):
            a_prev = acts[i]
            w = self.weights[i]
            # Propagate delta through the tanh of the previous (hidden) layer
            # BEFORE updating this layer's weights (standard backprop order).
            prev: list[float] | None = None
            if i > 0:
                prev = [0.0] * len(a_prev)
                for j in range(len(prev)):
                    s = sum(w[o][j] * delta[o] for o in range(len(delta)))
                    a = a_prev[j]
                    prev[j] = s * (1.0 - a * a)  # tanh'
            # Gradients for this layer.
            for o in range(len(w)):
                for j in range(len(w[o])):
                    g = delta[o] * a_prev[j] + weight_decay * w[o][j]
                    self._vel_w[i][o][j] = self.momentum * self._vel_w[i][o][j] - lr * g
                    w[o][j] += self._vel_w[i][o][j]
                self._vel_b[i][o] = self.momentum * self._vel_b[i][o] - lr * delta[o]
                self.biases[i][o] += self._vel_b[i][o]
            if prev is None:
                break
            delta = prev
        return err

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict:
        return {
            "kind": "deep_mlp",
            "layers": self.layers,
            "momentum": self.momentum,
            "weights": self.weights,
            "biases": self.biases,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeepMLP:
        net = cls(data["layers"], momentum=float(data.get("momentum", 0.9)))
        net.weights = [[[float(v) for v in row] for row in w] for w in data["weights"]]
        net.biases = [[float(v) for v in b] for b in data["biases"]]
        if [len(w) for w in net.weights] != net.layers[1:]:
            raise ValueError("weight shapes do not match declared layers")
        return net


class GatedReservoir:
    """Recurrent state-space model with input-selective gating.

    State update (the GHOST/Mamba distillation — the *gate depends on the
    input*, so the model chooses per-step how much history to keep):

        g_t = sigmoid(W_g · x_t + b_g)                (selective gate, learned)
        s_t = (1 − g_t) ⊙ s_{t−1} + g_t ⊙ tanh(W_in · x_t + W_rec · s_{t−1})
        y_t = W_out · [s_t ; x_t ; 1]                 (readout, learned)

    ``W_in``/``W_rec`` are fixed at construction with the reservoir scaled to a
    spectral radius < 1 (echo-state property → stable recurrence without
    backprop-through-time). Only the gate and the readout train online.
    """

    def __init__(
        self,
        n_inputs: int,
        *,
        n_state: int = 12,
        spectral_radius: float = 0.85,
        seed: int = 0,
    ) -> None:
        if n_inputs <= 0 or n_state <= 0:
            raise ValueError("n_inputs and n_state must be positive")
        self.n_inputs = n_inputs
        self.n_state = n_state
        rng = random.Random(seed)
        self.w_in = _rand_matrix(rng, n_state, n_inputs, 1.0 / math.sqrt(n_inputs))
        w_rec = _rand_matrix(rng, n_state, n_state, 1.0 / math.sqrt(n_state))
        scale = spectral_radius / max(1e-9, _power_iteration_radius(w_rec))
        self.w_rec = [[v * scale for v in row] for row in w_rec]
        # Learned parts: selective gate + linear readout over [state; input; 1].
        self.w_gate = _rand_matrix(rng, n_state, n_inputs, 0.1 / math.sqrt(n_inputs))
        self.b_gate = [0.0] * n_state
        self.w_out = [0.0] * (n_state + n_inputs + 1)
        self.state = [0.0] * n_state

    def reset_state(self) -> None:
        self.state = [0.0] * self.n_state

    # ------------------------------------------------------------------ dynamics
    def _advance(self, x: Sequence[float]) -> tuple[list[float], list[float], list[float]]:
        """Compute (new_state, gate, candidate) without committing them."""
        if len(x) != self.n_inputs:
            raise ValueError(f"expected input of length {self.n_inputs}, got {len(x)}")
        gate_z = [z + b for z, b in zip(_matvec(self.w_gate, x), self.b_gate, strict=True)]
        gate = [1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z)))) for z in gate_z]
        cand = _tanh_vec(
            [
                zi + zr
                for zi, zr in zip(_matvec(self.w_in, x), _matvec(self.w_rec, self.state), strict=True)
            ]
        )
        new_state = [
            (1.0 - g) * s + g * c for g, s, c in zip(gate, self.state, cand, strict=True)
        ]
        return new_state, gate, cand

    def _readout(self, state: Sequence[float], x: Sequence[float]) -> float:
        feats = list(state) + list(x) + [1.0]
        return sum(w * f for w, f in zip(self.w_out, feats, strict=True))

    def predict(self, x: Sequence[float]) -> float:
        """Prediction for input ``x`` given the current state (state unchanged)."""
        new_state, _, _ = self._advance(x)
        return self._readout(new_state, x)

    def train_step(
        self, x: Sequence[float], target: float, *, lr: float = 0.01, weight_decay: float = 1e-5
    ) -> float:
        """Advance the state, take one SGD step on readout + gate; return error."""
        new_state, gate, cand = self._advance(x)
        pred = self._readout(new_state, x)
        err = pred - target

        feats = list(new_state) + list(x) + [1.0]
        # Readout gradient (linear).
        for j, f in enumerate(feats):
            self.w_out[j] -= lr * (err * f + weight_decay * self.w_out[j])
        # Gate gradient: ∂pred/∂g_k = w_out[k] · (cand_k − s_{k,prev}) · g'(z).
        for k in range(self.n_state):
            dg = err * self.w_out[k] * (cand[k] - self.state[k]) * gate[k] * (1.0 - gate[k])
            for j in range(self.n_inputs):
                self.w_gate[k][j] -= lr * (dg * x[j] + weight_decay * self.w_gate[k][j])
            self.b_gate[k] -= lr * dg

        self.state = new_state
        return err

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict:
        return {
            "kind": "gated_reservoir",
            "n_inputs": self.n_inputs,
            "n_state": self.n_state,
            "w_in": self.w_in,
            "w_rec": self.w_rec,
            "w_gate": self.w_gate,
            "b_gate": self.b_gate,
            "w_out": self.w_out,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GatedReservoir:
        model = cls(int(data["n_inputs"]), n_state=int(data["n_state"]))
        for attr in ("w_in", "w_rec", "w_gate"):
            setattr(model, attr, [[float(v) for v in row] for row in data[attr]])
        model.b_gate = [float(v) for v in data["b_gate"]]
        model.w_out = [float(v) for v in data["w_out"]]
        model.state = [float(v) for v in data.get("state", [0.0] * model.n_state)]
        return model


def _power_iteration_radius(m: list[list[float]], iters: int = 50) -> float:
    """Approximate the spectral radius of a square matrix by power iteration."""
    n = len(m)
    rng = random.Random(1)
    v = [rng.gauss(0.0, 1.0) for _ in range(n)]
    radius = 0.0
    for _ in range(iters):
        w = _matvec(m, v)
        norm = math.sqrt(sum(x * x for x in w))
        if norm < 1e-12:
            return 0.0
        radius = norm / max(1e-12, math.sqrt(sum(x * x for x in v)))
        v = [x / norm for x in w]
    return radius
