"""Low-rank online adaptation of agent signals.

The swarm's agents reason through a *frozen*, hosted model (Claude via the API),
so we cannot fine-tune their weights. Instead we apply the LoRA idea one level
up: a tiny, trainable **low-rank correction on top of the frozen agents' raw
conviction**, learned online from realized trade outcomes.

For each signal we build a small feature vector (which agent produced it, its
direction, its raw conviction, its horizon). A :class:`LowRankAdapter` maps
that vector to a single conviction *delta*. Because the adapter is initialized
to a no-op, it starts by passing convictions through unchanged and only departs
from the agents' raw output as evidence accumulates.

**Learning objective (calibration).** After a signal's horizon elapses we
observe the realized return. We nudge the *effective* conviction toward a
calibration target:

* the signal was directionally **right** → target conviction ≈ how big the move
  was (so confident-and-correct is rewarded);
* the signal was directionally **wrong** → target conviction ≈ 0 (confident-and-
  wrong is penalized).

Over many outcomes the low-rank head learns, e.g., "the fundamental agent's
bullish swing calls are systematically over/under-confident" and corrects for
it — without ever touching the base model.
"""

from __future__ import annotations

from pathlib import Path

from aoa.adapt.lowrank import LowRankAdapter
from aoa.agents.base import Direction, Signal

# Fixed feature layout. Unknown agents fall into the trailing "other" slot.
_AGENTS = ("technical", "fundamental", "options", "portfolio", "scanner")
_HORIZONS = ("intraday", "swing", "position")
# bias + agent one-hot(+other) + direction-sign + raw-conviction + horizon one-hot
_IN_FEATURES = 1 + (len(_AGENTS) + 1) + 1 + 1 + len(_HORIZONS)


def _dir_sign(direction: str) -> float:
    if direction == Direction.BULLISH.value:
        return 1.0
    if direction == Direction.BEARISH.value:
        return -1.0
    return 0.0


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


class SignalAdapter:
    """A LoRA-style conviction recalibrator for agent signals.

    Parameters
    ----------
    rank, alpha:
        Low-rank adapter hyperparameters (see :class:`LowRankAdapter`).
    lr:
        Online SGD learning rate per recorded outcome.
    return_scale:
        The move size (as a fraction, e.g. ``0.05`` = 5%) treated as a "full
        conviction" outcome. Realized returns are normalized by this.
    """

    def __init__(
        self,
        *,
        rank: int = 4,
        alpha: float = 8.0,
        lr: float = 0.05,
        return_scale: float = 0.05,
        seed: int = 0,
    ) -> None:
        self.lr = lr
        self.return_scale = max(1e-6, return_scale)
        self.updates = 0
        self.core = LowRankAdapter(_IN_FEATURES, 1, rank=rank, alpha=alpha, seed=seed)

    # ----------------------------------------------------------------- features
    def featurize(
        self, *, agent: str, direction: str, conviction: float, horizon: str = "swing"
    ) -> list[float]:
        feats = [1.0]  # bias
        agent_oh = [0.0] * (len(_AGENTS) + 1)
        agent_oh[_AGENTS.index(agent) if agent in _AGENTS else len(_AGENTS)] = 1.0
        feats += agent_oh
        feats.append(_dir_sign(direction))
        feats.append(float(conviction))
        horizon_oh = [0.0] * len(_HORIZONS)
        h_idx = _HORIZONS.index(horizon) if horizon in _HORIZONS else _HORIZONS.index("swing")
        horizon_oh[h_idx] = 1.0
        feats += horizon_oh
        return feats

    # ------------------------------------------------------------------ inference
    def adjusted_conviction(
        self, *, agent: str, direction: str, conviction: float, horizon: str = "swing"
    ) -> tuple[float, float]:
        """Return ``(adjusted_conviction, raw_delta)``.

        The adjusted value is clamped to ``[0, 1]``; ``raw_delta`` is the
        unclamped low-rank correction (handy for journaling/inspection).
        """
        x = self.featurize(
            agent=agent, direction=direction, conviction=conviction, horizon=horizon
        )
        delta = self.core.delta(x)[0]
        return _clamp01(conviction + delta), delta

    def adapt_signal(self, signal: Signal) -> Signal:
        """Return a copy of ``signal`` with recalibrated conviction.

        Neutral signals are returned unchanged (there is no edge to size).
        """
        if signal.direction is Direction.NEUTRAL:
            return signal
        adjusted, delta = self.adjusted_conviction(
            agent=signal.source,
            direction=signal.direction.value,
            conviction=signal.conviction,
            horizon=signal.horizon,
        )
        tags = list(signal.tags)
        if "adapted" not in tags:
            tags.append("adapted")
        return Signal(
            symbol=signal.symbol,
            source=signal.source,
            direction=signal.direction,
            conviction=adjusted,
            rationale=signal.rationale,
            horizon=signal.horizon,
            key_levels=dict(signal.key_levels),
            tags=tags,
        )

    # ------------------------------------------------------------------- learning
    def record_outcome(
        self,
        *,
        agent: str,
        direction: str,
        conviction: float,
        realized_return: float,
        horizon: str = "swing",
    ) -> float:
        """Learn from one realized outcome; return the calibration error.

        ``realized_return`` is the return of the underlying over the signal's
        horizon (e.g. ``+0.02`` for +2%). Neutral signals carry no directional
        bet and are ignored (returns ``0.0``).
        """
        sign = _dir_sign(direction)
        if sign == 0.0:
            return 0.0

        x = self.featurize(
            agent=agent, direction=direction, conviction=conviction, horizon=horizon
        )
        delta = self.core.delta(x)[0]
        predicted = _clamp01(conviction + delta)

        directional = sign * realized_return
        magnitude = min(1.0, abs(realized_return) / self.return_scale)
        target = magnitude if directional > 0 else 0.0

        error = predicted - target  # ∂(½·err²)/∂predicted
        # Kill the gradient when the clamp is saturated against the error's
        # direction (the parameter can't usefully move further that way).
        grad = error
        if predicted <= 0.0 and error < 0.0:
            grad = 0.0
        elif predicted >= 1.0 and error > 0.0:
            grad = 0.0

        if grad != 0.0:
            self.core.sgd_step(x, [grad], lr=self.lr, weight_decay=1e-4)
        self.updates += 1
        return error

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict:
        return {
            "version": 1,
            "lr": self.lr,
            "return_scale": self.return_scale,
            "updates": self.updates,
            "core": self.core.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SignalAdapter:
        adapter = cls(lr=float(data.get("lr", 0.05)),
                      return_scale=float(data.get("return_scale", 0.05)))
        adapter.updates = int(data.get("updates", 0))
        adapter.core = LowRankAdapter.from_dict(data["core"])
        if adapter.core.in_features != _IN_FEATURES or adapter.core.out_features != 1:
            raise ValueError("persisted adapter does not match the current feature layout")
        return adapter

    def save(self, path: str | Path) -> None:
        import json

        Path(path).write_text(json.dumps(self.to_dict()))

    @classmethod
    def load(cls, path: str | Path) -> SignalAdapter:
        import json

        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def load_or_new(cls, path: str | Path | None, **kwargs) -> SignalAdapter:
        """Load from ``path`` if it exists, else build a fresh adapter."""
        import json

        if path and Path(path).exists():
            try:
                return cls.load(path)
            except (ValueError, KeyError, json.JSONDecodeError):  # corrupt/incompatible
                pass
        return cls(**kwargs)
