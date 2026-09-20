"""The crypto trader swarm: many specialized traders, one Hedge ensemble.

The multi-trader design applies the account's own repos (see
``docs/design/account-repo-mesh.md``):

* **AutoHedge / OpenAI_Agent_Swarm** — a swarm of specialized traders whose
  votes are fused by a supervisor. Our supervisor is the classic **Hedge
  (multiplicative-weights) algorithm**: each trader's weight decays
  exponentially with its realized directional loss, so capital-of-trust flows
  to whoever has actually been right.
* **deepstock / Stock-Price-Prediction / Deep-Learning--Stock-Market-Prediction**
  — deep feed-forward and recurrent predictors (:mod:`aoa.crypto.deep`).
* **GHOST** — the input-selective gated recurrence inside
  :class:`~aoa.crypto.deep.GatedReservoir`.
* **Stock-Market-App** — a classical online autoregressive forecaster as the
  statistical baseline trader.
* **Pairs-Trading-Analyzer** — a relative-value trader on the log-ratio
  z-score against a partner asset (cointegration-flavored mean reversion).
* **lifelines / scikit-survival** — the :class:`~aoa.crypto.survival.BracketSurvival`
  gate estimating P(+32% before −26%) per regime.

Every trader implements ``decide(feats) -> (action, conviction)`` and
``learn(feats, next_ret)``; the ensemble exposes the same protocol (plus
persistence), so the backtester can drive a single trainer or the whole swarm
interchangeably.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from aoa.adapt.lowrank import LowRankAdapter
from aoa.connectome.elegans import MarketWorm
from aoa.crypto.assets import CryptoAsset
from aoa.crypto.deep import DeepMLP, GatedReservoir
from aoa.crypto.survival import BracketSurvival
from aoa.crypto.training import (
    _RETURN_SCALE,
    N_FEATURES,
    DayFeatures,
    PatternMemory,
)

Action = str  # "buy" | "sell" | "hold"


def _score_to_action(score: float, *, threshold: float = 0.15) -> tuple[Action, float]:
    conviction = min(1.0, abs(score))
    if score > threshold:
        return "buy", conviction
    if score < -threshold:
        return "sell", conviction
    return "hold", 0.0


class BaseTrader:
    """Common trader protocol. ``name`` must be unique within a roster."""

    name = "base"

    def decide(self, feats: DayFeatures) -> tuple[Action, float]:  # pragma: no cover
        raise NotImplementedError

    def learn(self, feats: DayFeatures, next_ret: float) -> None:  # pragma: no cover
        raise NotImplementedError

    def state_dict(self) -> dict:
        return {}

    def load_state(self, data: dict) -> None:
        pass


class MomentumHeadTrader(BaseTrader):
    """The original LoRA-head calibrated momentum predictor."""

    name = "momentum-head"

    def __init__(self, *, seed: int = 7, lr: float = 0.02) -> None:
        self.lr = lr
        self.head = LowRankAdapter(N_FEATURES, 1, rank=4, alpha=8.0, seed=seed)

    def decide(self, feats: DayFeatures) -> tuple[Action, float]:
        pred = self.head.delta(feats.vector())[0]
        return _score_to_action(pred)

    def learn(self, feats: DayFeatures, next_ret: float) -> None:
        target = max(-1.0, min(1.0, next_ret / _RETURN_SCALE))
        out = self.head.delta(feats.vector())[0]
        self.head.sgd_step(feats.vector(), [out - target], lr=self.lr, weight_decay=1e-4)

    def state_dict(self) -> dict:
        return self.head.to_dict()

    def load_state(self, data: dict) -> None:
        self.head = LowRankAdapter.from_dict(data)


class DeepMLPTrader(BaseTrader):
    """Deep feed-forward predictor over features + recent-return lags."""

    def __init__(self, *, hidden: tuple[int, ...] = (16, 8), seed: int = 11, lr: float = 0.01):
        self.name = f"deep-mlp-{'x'.join(str(h) for h in hidden)}"
        self.lr = lr
        self.n_lags = 8
        self._lags: list[float] = []
        self.net = DeepMLP([N_FEATURES + self.n_lags, *hidden, 1], seed=seed)

    def _input(self, feats: DayFeatures) -> list[float]:
        lags = list(self._lags[-self.n_lags :])
        lags = [0.0] * (self.n_lags - len(lags)) + lags
        return feats.vector() + lags

    def decide(self, feats: DayFeatures) -> tuple[Action, float]:
        return _score_to_action(self.net.predict(self._input(feats)))

    def learn(self, feats: DayFeatures, next_ret: float) -> None:
        target = max(-1.0, min(1.0, next_ret / _RETURN_SCALE))
        self.net.train_step(self._input(feats), target, lr=self.lr)
        self._lags.append(max(-1.0, min(1.0, feats.ret1 / _RETURN_SCALE)))
        if len(self._lags) > 4 * self.n_lags:
            self._lags = self._lags[-self.n_lags :]

    def state_dict(self) -> dict:
        return {"net": self.net.to_dict(), "lags": self._lags[-self.n_lags :]}

    def load_state(self, data: dict) -> None:
        self.net = DeepMLP.from_dict(data["net"])
        self._lags = [float(v) for v in data.get("lags", [])]


class ReservoirTrader(BaseTrader):
    """Gated recurrent state-space predictor (the GHOST/Mamba distillation)."""

    name = "gated-reservoir"

    def __init__(self, *, n_state: int = 12, seed: int = 23, lr: float = 0.01) -> None:
        self.lr = lr
        self.model = GatedReservoir(N_FEATURES, n_state=n_state, seed=seed)

    def decide(self, feats: DayFeatures) -> tuple[Action, float]:
        return _score_to_action(self.model.predict(feats.vector()))

    def learn(self, feats: DayFeatures, next_ret: float) -> None:
        target = max(-1.0, min(1.0, next_ret / _RETURN_SCALE))
        self.model.train_step(feats.vector(), target, lr=self.lr)

    def state_dict(self) -> dict:
        return self.model.to_dict()

    def load_state(self, data: dict) -> None:
        self.model = GatedReservoir.from_dict(data)


class WormTrader(BaseTrader):
    """The connectome worm as a swarm member (reflexive regime trader)."""

    name = "connectome-worm"

    def __init__(self) -> None:
        self.worm = MarketWorm()
        self.memory = PatternMemory()

    def decide(self, feats: DayFeatures) -> tuple[Action, float]:
        decision = self.worm.decide(feats.stimulus(regime_heat=self.memory.regime_heat(feats)))
        return decision.action, decision.conviction

    def learn(self, feats: DayFeatures, next_ret: float) -> None:
        action, _ = self.decide(feats)
        if action != "hold":
            signed = next_ret if action == "buy" else -next_ret
            self.worm.reinforce(max(-1.0, min(1.0, signed / _RETURN_SCALE)))
        self.memory.observe(feats, next_ret)

    def state_dict(self) -> dict:
        return {"worm": self.worm.connectome.to_dict(), "memory": self.memory.to_dict()}

    def load_state(self, data: dict) -> None:
        from aoa.connectome.engine import Connectome

        self.worm = MarketWorm(Connectome.from_dict(data["worm"]))
        self.memory = PatternMemory.from_dict(data["memory"])


class MemoryTrader(BaseTrader):
    """Trades the statistical edge from the persistent pattern memory."""

    name = "pattern-memory"

    def __init__(self) -> None:
        self.memory = PatternMemory()

    def decide(self, feats: DayFeatures) -> tuple[Action, float]:
        return _score_to_action(self.memory.edge(feats), threshold=0.08)

    def learn(self, feats: DayFeatures, next_ret: float) -> None:
        self.memory.observe(feats, next_ret)

    def state_dict(self) -> dict:
        return self.memory.to_dict()

    def load_state(self, data: dict) -> None:
        self.memory = PatternMemory.from_dict(data)


class ARTrader(BaseTrader):
    """Classical online AR(p) forecaster (the Stock-Market-App baseline)."""

    name = "ar-forecaster"

    def __init__(self, *, p: int = 5, lr: float = 0.02) -> None:
        self.p = p
        self.lr = lr
        self.coef = [0.0] * (p + 1)  # + bias
        self._rets: list[float] = []

    def _x(self) -> list[float]:
        lags = list(self._rets[-self.p :])
        lags = [0.0] * (self.p - len(lags)) + lags
        return [1.0, *lags]

    def decide(self, feats: DayFeatures) -> tuple[Action, float]:
        x = self._x()
        pred = sum(c * v for c, v in zip(self.coef, x, strict=True))
        return _score_to_action(pred, threshold=0.1)

    def learn(self, feats: DayFeatures, next_ret: float) -> None:
        x = self._x()
        pred = sum(c * v for c, v in zip(self.coef, x, strict=True))
        target = max(-1.0, min(1.0, next_ret / _RETURN_SCALE))
        err = pred - target
        for i, v in enumerate(x):
            self.coef[i] -= self.lr * (err * v + 1e-4 * self.coef[i])
        self._rets.append(max(-1.0, min(1.0, feats.ret1 / _RETURN_SCALE)))
        if len(self._rets) > 4 * self.p:
            self._rets = self._rets[-self.p :]

    def state_dict(self) -> dict:
        return {"coef": self.coef, "rets": self._rets[-self.p :]}

    def load_state(self, data: dict) -> None:
        self.coef = [float(v) for v in data["coef"]]
        self._rets = [float(v) for v in data.get("rets", [])]


class PairsTrader(BaseTrader):
    """Relative-value mean reversion on the log-ratio vs a partner asset.

    The Engle-Granger two-step from Pairs-Trading-Analyzer collapses, for two
    series we deliberately pair by economic similarity (BTC↔ETH, SOL↔ETH,
    XRP↔BTC), into a rolling z-score of the log price ratio: stretch low →
    this asset is cheap vs its partner → buy; stretch high → exit. Without
    partner closes (``update_pair`` never called) the trader abstains.
    """

    def __init__(self, partner_code: str = "", *, window: int = 60) -> None:
        self.name = f"pairs-vs-{partner_code.lower() or 'none'}"
        self.partner_code = partner_code
        self.window = window
        self._ratios: list[float] = []
        self._z: float | None = None

    def update_pair(self, own_close: float, partner_close: float) -> None:
        if own_close <= 0 or partner_close <= 0:
            return
        self._ratios.append(math.log(own_close / partner_close))
        if len(self._ratios) > 4 * self.window:
            self._ratios = self._ratios[-self.window :]
        sample = self._ratios[-self.window :]
        if len(sample) < max(10, self.window // 3):
            self._z = None
            return
        mu = sum(sample) / len(sample)
        var = sum((r - mu) ** 2 for r in sample) / (len(sample) - 1)
        std = math.sqrt(var)
        self._z = 0.0 if std < 1e-12 else (sample[-1] - mu) / std

    def decide(self, feats: DayFeatures) -> tuple[Action, float]:
        if self._z is None:
            return "hold", 0.0
        # Cheap vs partner (z < -1) → buy; rich (z > +1) → sell/exit.
        return _score_to_action(-self._z / 2.0, threshold=0.5)

    def learn(self, feats: DayFeatures, next_ret: float) -> None:
        pass  # purely statistical; updated via update_pair

    def state_dict(self) -> dict:
        return {"partner": self.partner_code, "ratios": self._ratios[-self.window :]}

    def load_state(self, data: dict) -> None:
        self.partner_code = str(data.get("partner", self.partner_code))
        self._ratios = [float(v) for v in data.get("ratios", [])]
        if self._ratios:
            # Recompute the z-score from the restored window.
            last = self._ratios[-1]
            sample = self._ratios[-self.window :]
            mu = sum(sample) / len(sample)
            var = sum((r - mu) ** 2 for r in sample) / max(1, len(sample) - 1)
            std = math.sqrt(var)
            self._z = 0.0 if std < 1e-12 else (last - mu) / std


# --- the ensemble ---------------------------------------------------------------

PAIR_PARTNERS = {"BTC": "ETH", "ETH": "BTC", "SOL": "ETH", "XRP": "BTC"}


def default_roster(asset: CryptoAsset) -> list[BaseTrader]:
    """The full swarm for one asset."""
    return [
        MomentumHeadTrader(seed=7),
        DeepMLPTrader(hidden=(16, 8), seed=11),
        DeepMLPTrader(hidden=(24, 12, 6), seed=13),
        ReservoirTrader(n_state=12, seed=23),
        WormTrader(),
        MemoryTrader(),
        ARTrader(p=5),
        PairsTrader(PAIR_PARTNERS.get(asset.code, "")),
    ]


@dataclass(frozen=True)
class EnsembleDecision:
    action: Action
    conviction: float
    votes: dict[str, tuple[Action, float]]
    weights: dict[str, float]
    gate_open: bool
    gate_odds: float


class HedgeEnsemble:
    """Multiplicative-weights supervisor over the trader swarm.

    Weight update (Hedge): after each day, every non-abstaining trader incurs
    loss ``ℓ ∈ [0, 1]`` — 0 when its vote matched the realized direction, 1
    when it opposed it, 0.5 for holds — and ``w ← w · exp(−η · ℓ)``, then
    weights renormalize. Persistent across sessions. The survival gate can
    veto ensemble *entries* (never exits).
    """

    def __init__(
        self,
        asset: CryptoAsset,
        *,
        roster: list[BaseTrader] | None = None,
        eta: float = 0.10,
        model_dir: str | Path = "data/crypto/models",
        survival: BracketSurvival | None = None,
    ) -> None:
        self.asset = asset
        self.eta = eta
        self.traders = roster if roster is not None else default_roster(asset)
        names = [t.name for t in self.traders]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate trader names in roster: {names}")
        self.weights: dict[str, float] = {n: 1.0 / len(names) for n in names}
        self.survival = survival or BracketSurvival()
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.days_learned = 0
        self.load_state()

    # ------------------------------------------------------------------ voting
    def decide(self, feats: DayFeatures) -> tuple[Action, float]:
        decision = self.decide_full(feats)
        return decision.action, decision.conviction

    def decide_full(self, feats: DayFeatures) -> EnsembleDecision:
        votes: dict[str, tuple[Action, float]] = {}
        score = 0.0
        active_weight = 0.0
        for trader in self.traders:
            action, conviction = trader.decide(feats)
            votes[trader.name] = (action, conviction)
            w = self.weights[trader.name]
            if action == "buy":
                score += w * conviction
                active_weight += w
            elif action == "sell":
                score -= w * conviction
                active_weight += w
        if active_weight > 0:
            score /= active_weight
        action, conviction = _score_to_action(score, threshold=0.12)
        odds, _n = self.survival.win_odds(feats)
        gate_open = self.survival.allows(feats)
        if action == "buy" and not gate_open:
            action, conviction = "hold", 0.0
        return EnsembleDecision(
            action=action,
            conviction=conviction,
            votes=votes,
            weights=dict(self.weights),
            gate_open=gate_open,
            gate_odds=odds,
        )

    # ---------------------------------------------------------------- learning
    def learn(self, feats: DayFeatures, next_ret: float, candle=None) -> None:
        """One day of swarm learning: Hedge reweighting + every trader learns."""
        direction = 1.0 if next_ret > 0 else (-1.0 if next_ret < 0 else 0.0)
        for trader in self.traders:
            action, conviction = trader.decide(feats)
            if direction != 0.0:
                if action == "hold":
                    loss = 0.5
                else:
                    vote = 1.0 if action == "buy" else -1.0
                    # Loss in [0,1]: right & confident → ~0; wrong & confident → ~1.
                    loss = 0.5 * (1.0 - vote * direction * conviction)
                self.weights[trader.name] *= math.exp(-self.eta * loss)
            trader.learn(feats, next_ret)
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {n: w / total for n, w in self.weights.items()}
        # Survival tracker: resolve pending races, then open today's virtual entry.
        if candle is not None:
            self.survival.observe_candle(candle)
            self.survival.open_virtual(feats, candle.close)
        self.days_learned += 1

    def update_pairs(self, own_close: float, partner_close: float) -> None:
        for trader in self.traders:
            if isinstance(trader, PairsTrader):
                trader.update_pair(own_close, partner_close)

    # ------------------------------------------------------------------ training
    def train(
        self,
        candles,
        *,
        partner_closes: dict | None = None,
        save: bool = True,
    ) -> dict:
        """Day-by-day walk over ``candles``: every trader learns, Hedge reweights.

        Returns a summary including each trader's honest walk-forward hit rate
        (decisions are scored *before* the day's outcome is learned).
        """
        from aoa.crypto.training import extract_features

        hits: dict[str, int] = {t.name: 0 for t in self.traders}
        totals: dict[str, int] = {t.name: 0 for t in self.traders}
        for i in range(1, len(candles) - 1):
            candle = candles[i]
            if candle.close <= 0:
                continue
            if partner_closes:
                partner = partner_closes.get(candle.day)
                if partner:
                    self.update_pairs(candle.close, partner)
            feats = extract_features(candles, i)
            if feats is None:
                continue
            next_ret = candles[i + 1].close / candle.close - 1.0
            for trader in self.traders:
                action, _ = trader.decide(feats)
                if action != "hold" and next_ret != 0.0:
                    totals[trader.name] += 1
                    signed = next_ret if action == "buy" else -next_ret
                    if signed > 0:
                        hits[trader.name] += 1
            self.learn(feats, next_ret, candle)
        if save:
            self.save_state()
        return {
            "asset": self.asset.code,
            "days_learned": self.days_learned,
            "weights": {n: round(w, 4) for n, w in sorted(self.weights.items())},
            "hit_rates": {
                n: round(hits[n] / totals[n], 4) if totals[n] else None for n in hits
            },
            "decisions": totals,
            "survival": self.survival.summary(),
        }

    # ------------------------------------------------------------ persistence
    def _path(self) -> Path:
        return self.model_dir / f"{self.asset.code.lower()}_ensemble.json"

    def save_state(self) -> None:
        payload = {
            "version": 1,
            "asset": self.asset.code,
            "eta": self.eta,
            "days_learned": self.days_learned,
            "weights": self.weights,
            "survival": self.survival.to_dict(),
            "traders": {t.name: t.state_dict() for t in self.traders},
        }
        self._path().write_text(json.dumps(payload))

    def load_state(self) -> bool:
        path = self._path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            return False
        stored = data.get("weights", {})
        for name in self.weights:
            if name in stored:
                self.weights[name] = float(stored[name])
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {n: w / total for n, w in self.weights.items()}
        if "survival" in data:
            self.survival = BracketSurvival.from_dict(data["survival"])
        self.days_learned = int(data.get("days_learned", 0))
        states = data.get("traders", {})
        for trader in self.traders:
            if trader.name in states and states[trader.name]:
                try:
                    trader.load_state(states[trader.name])
                except (KeyError, ValueError):  # incompatible layout — start fresh
                    pass
        return True

    def describe(self) -> dict:
        return {
            "asset": self.asset.code,
            "traders": [t.name for t in self.traders],
            "weights": {n: round(w, 4) for n, w in sorted(self.weights.items())},
            "days_learned": self.days_learned,
            "survival_regimes": len(self.survival.outcomes),
        }
