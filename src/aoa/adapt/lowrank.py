"""Framework-free low-rank adaptation core.

This implements the LoRA reparameterization

    ΔW = (α / r) · A · B

as a *trainable, low-rank correction* applied on top of a frozen base output.
Only ``A`` (out × r) and ``B`` (r × in) are learned — a tiny number of
parameters relative to a full ``out × in`` matrix — which is the whole point of
low-rank adaptation.

It deliberately has **no third-party dependencies** (no ``torch``/``numpy``), so
it runs anywhere the rest of the swarm runs. The matrices are plain Python
lists; the math is small (rank is typically 2–8 and feature dims are tiny), so
pure Python is more than fast enough here. For heavyweight neural-net use, see
:mod:`aoa.adapt.torch_lora`, which expresses the same idea over ``torch``.

Following the LoRA paper, ``B`` is initialized to small random values and ``A``
to zeros, so the adapter starts as an exact no-op (ΔW = 0) and only departs from
the base output as it learns.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Sequence
from pathlib import Path

Vector = list[float]
Matrix = list[list[float]]


def _zeros(rows: int, cols: int) -> Matrix:
    return [[0.0] * cols for _ in range(rows)]


def _matvec(matrix: Matrix, vec: Sequence[float]) -> Vector:
    """Matrix (rows × cols) · vec (cols) → vector (rows)."""
    return [sum(m_ij * x_j for m_ij, x_j in zip(row, vec, strict=True)) for row in matrix]


class LowRankAdapter:
    """A learnable low-rank linear correction ``ΔW = scaling · A · B``.

    Parameters
    ----------
    in_features, out_features:
        Shape of the (frozen) base linear map this adapter corrects.
    rank:
        The low rank ``r``. Smaller = fewer parameters, less capacity.
    alpha:
        LoRA scaling numerator; the effective scale is ``alpha / rank``.
    seed:
        Seed for the deterministic initialization of ``B``.
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        rank: int = 4,
        alpha: float = 8.0,
        *,
        seed: int = 0,
    ) -> None:
        if in_features <= 0 or out_features <= 0:
            raise ValueError("in_features and out_features must be positive")
        if rank <= 0:
            raise ValueError("rank must be a positive integer")
        self.in_features = in_features
        self.out_features = out_features
        self.rank = rank
        self.alpha = float(alpha)
        self.scaling = self.alpha / rank

        rng = random.Random(seed)
        std = 1.0 / math.sqrt(in_features)
        # B: r × in, small Gaussian.  A: out × r, zeros => initial ΔW is exactly 0.
        self.B: Matrix = [
            [rng.gauss(0.0, std) for _ in range(in_features)] for _ in range(rank)
        ]
        self.A: Matrix = _zeros(out_features, rank)

    # ------------------------------------------------------------------ forward
    def delta(self, x: Sequence[float]) -> Vector:
        """Return the low-rank correction ``scaling · A · (B · x)``."""
        if len(x) != self.in_features:
            raise ValueError(
                f"expected input of length {self.in_features}, got {len(x)}"
            )
        bx = _matvec(self.B, x)  # length r
        abx = _matvec(self.A, bx)  # length out
        return [self.scaling * v for v in abx]

    def apply(self, x: Sequence[float], base: Sequence[float]) -> Vector:
        """Return ``base + delta(x)`` elementwise."""
        if len(base) != self.out_features:
            raise ValueError(
                f"expected base of length {self.out_features}, got {len(base)}"
            )
        return [b + d for b, d in zip(base, self.delta(x), strict=True)]

    def effective_weight(self) -> Matrix:
        """The dense ``out × in`` matrix this adapter is equivalent to (ΔW).

        Useful for inspection/merging; not needed on the hot path.
        """
        weight = _zeros(self.out_features, self.in_features)
        for o in range(self.out_features):
            for j in range(self.in_features):
                acc = 0.0
                for k in range(self.rank):
                    acc += self.A[o][k] * self.B[k][j]
                weight[o][j] = self.scaling * acc
        return weight

    # ----------------------------------------------------------------- training
    def sgd_step(
        self,
        x: Sequence[float],
        grad_out: Sequence[float],
        *,
        lr: float = 0.05,
        weight_decay: float = 0.0,
    ) -> None:
        """One SGD update of ``A`` and ``B`` given ∂L/∂output = ``grad_out``.

        Both gradients are computed from the *current* parameters before either
        matrix is updated (standard simultaneous SGD). Because ``A`` starts at
        zero, the first update moves only ``A``; ``B`` begins adapting once
        ``A`` is non-zero — the usual LoRA training dynamic.
        """
        if len(grad_out) != self.out_features:
            raise ValueError(
                f"expected grad_out of length {self.out_features}, got {len(grad_out)}"
            )
        s = self.scaling
        bx = _matvec(self.B, x)  # length r, uses current B

        # ∂L/∂A[o][k] = scaling · grad_out[o] · (B·x)[k]
        grad_a: Matrix = [
            [s * grad_out[o] * bx[k] for k in range(self.rank)]
            for o in range(self.out_features)
        ]
        # combine[k] = Σ_o grad_out[o] · A[o][k]   (uses current A)
        combine = [
            sum(grad_out[o] * self.A[o][k] for o in range(self.out_features))
            for k in range(self.rank)
        ]
        # ∂L/∂B[k][j] = scaling · combine[k] · x[j]
        grad_b: Matrix = [
            [s * combine[k] * x[j] for j in range(self.in_features)]
            for k in range(self.rank)
        ]

        for o in range(self.out_features):
            for k in range(self.rank):
                upd = grad_a[o][k] + weight_decay * self.A[o][k]
                self.A[o][k] -= lr * upd
        for k in range(self.rank):
            for j in range(self.in_features):
                upd = grad_b[k][j] + weight_decay * self.B[k][j]
                self.B[k][j] -= lr * upd

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict:
        return {
            "in_features": self.in_features,
            "out_features": self.out_features,
            "rank": self.rank,
            "alpha": self.alpha,
            "A": self.A,
            "B": self.B,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LowRankAdapter:
        adapter = cls(
            int(data["in_features"]),
            int(data["out_features"]),
            int(data["rank"]),
            float(data["alpha"]),
        )
        adapter.A = [[float(v) for v in row] for row in data["A"]]
        adapter.B = [[float(v) for v in row] for row in data["B"]]
        if len(adapter.A) != adapter.out_features or len(adapter.B) != adapter.rank:
            raise ValueError("adapter matrices do not match declared shape")
        return adapter

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict()))

    @classmethod
    def load(cls, path: str | Path) -> LowRankAdapter:
        return cls.from_dict(json.loads(Path(path).read_text()))
