"""Day-by-day walk-forward crypto learner with persistent pattern memory.

This is deliberately *not* a batch fit over the whole tape. The trainer walks
the calendar one day at a time from 2007-07-17 — including the days before an
asset existed — and on each market day it:

1. extracts features from history *up to that day only* (no lookahead),
2. updates :class:`PatternMemory` — the running statistical memory of streak
   continuation, seasonality, volatility-regime behaviour, drawdown response,
   and big-move follow-through,
3. asks the connectome worm for a motor decision and lets it experience the
   realized next-day return as a dopamine reward (its synapses shift), and
4. takes one online SGD step on a :class:`~aoa.adapt.lowrank.LowRankAdapter`
   head that learns to predict the next day's return from the features.

Everything the learner knows persists as JSON (memory, adapter weights, and
the plasticity-shifted connectome) so later sessions resume where this one
left off.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from aoa.adapt.lowrank import LowRankAdapter
from aoa.connectome.elegans import MarketStimulus, MarketWorm
from aoa.crypto.assets import TRAINING_EPOCH, CryptoAsset
from aoa.crypto.history import DailyCandle, calendar_walk

# Feature layout for the low-rank prediction head:
# bias, ret1, ret5, ret20, vol_shock, drawdown, capitulation, streak_norm,
# dow sin/cos, month sin/cos.
N_FEATURES = 12
_RETURN_SCALE = 0.05  # 5% daily move == full-scale target


def _tanh(x: float) -> float:
    return math.tanh(x)


@dataclass(frozen=True)
class DayFeatures:
    """No-lookahead features for one market day."""

    day: date
    ret1: float
    ret5: float
    ret20: float
    vol_shock: float  # [0,1] short-vol vs long-vol expansion
    drawdown: float  # [0,1] below trailing 90d peak
    capitulation: float  # [0,1]
    streak: int  # signed run of consecutive up(+)/down(−) closes

    def vector(self) -> list[float]:
        dow = self.day.weekday()
        month = self.day.month - 1
        return [
            1.0,
            _tanh(self.ret1 / _RETURN_SCALE),
            _tanh(self.ret5 / (2 * _RETURN_SCALE)),
            _tanh(self.ret20 / (4 * _RETURN_SCALE)),
            self.vol_shock,
            self.drawdown,
            self.capitulation,
            _tanh(self.streak / 5.0),
            math.sin(2 * math.pi * dow / 7),
            math.cos(2 * math.pi * dow / 7),
            math.sin(2 * math.pi * month / 12),
            math.cos(2 * math.pi * month / 12),
        ]

    def stimulus(self, *, regime_heat: float = 0.0) -> MarketStimulus:
        return MarketStimulus(
            momentum_short=_tanh(self.ret5 / (2 * _RETURN_SCALE)),
            momentum_long=_tanh(self.ret20 / (4 * _RETURN_SCALE)),
            vol_shock=self.vol_shock,
            drawdown=self.drawdown,
            capitulation=self.capitulation,
            regime_heat=regime_heat,
        )


def extract_features(candles: Sequence[DailyCandle], idx: int) -> DayFeatures | None:
    """Features for ``candles[idx]`` using only candles ``<= idx``."""
    if idx < 1:
        return None
    window = candles[max(0, idx - 99) : idx + 1]
    closes = [c.close for c in window]
    day = candles[idx].day

    def ret(n: int) -> float:
        if len(closes) <= n or closes[-1 - n] <= 0:
            return 0.0
        return closes[-1] / closes[-1 - n] - 1.0

    rets = [
        closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0
    ]

    def vol(n: int) -> float:
        sample = rets[-n:]
        if len(sample) < 2:
            return 0.0
        mu = sum(sample) / len(sample)
        return (sum((r - mu) ** 2 for r in sample) / (len(sample) - 1)) ** 0.5

    vol_short, vol_long = vol(10), vol(60)
    vol_shock = 0.0
    if vol_long > 0:
        vol_shock = max(0.0, min(1.0, (vol_short / vol_long - 1.0) / 2.0))

    peak = max(closes[-90:])
    drawdown = max(0.0, min(1.0, 1.0 - closes[-1] / peak)) if peak > 0 else 0.0

    streak = 0
    for i in range(len(closes) - 1, 0, -1):
        step = closes[i] - closes[i - 1]
        if step > 0:
            if streak < 0:
                break
            streak += 1
        elif step < 0:
            if streak > 0:
                break
            streak -= 1
        else:
            break

    r1 = ret(1)
    capitulation = min(1.0, r1 / 0.05) if (drawdown > 0.35 and r1 > 0.0) else 0.0

    return DayFeatures(
        day=day,
        ret1=r1,
        ret5=ret(5),
        ret20=ret(20),
        vol_shock=vol_shock,
        drawdown=drawdown,
        capitulation=capitulation,
        streak=streak,
    )


# --- persistent pattern memory ------------------------------------------------


def _bucket_stats() -> dict:
    return {"n": 0, "sum": 0.0, "up": 0}


def _observe(stats: dict, next_ret: float) -> None:
    stats["n"] += 1
    stats["sum"] += next_ret
    if next_ret > 0:
        stats["up"] += 1


def _summ(stats: dict) -> dict:
    n = stats["n"]
    return {
        "n": n,
        "mean_next_ret": (stats["sum"] / n) if n else 0.0,
        "p_up": (stats["up"] / n) if n else 0.0,
    }


@dataclass
class PatternMemory:
    """Running statistics of the patterns seen day by day.

    All keys are strings so the memory round-trips through JSON unchanged.
    """

    asset: str = ""
    days_walked: int = 0
    market_days: int = 0
    pre_genesis_days: int = 0
    pre_market_days: int = 0
    gap_days: int = 0
    first_day: str = ""
    last_day: str = ""
    # streak length (signed, clamped ±7, as str) -> next-day stats
    streaks: dict[str, dict] = field(default_factory=dict)
    # month "1".."12" -> next-day stats
    months: dict[str, dict] = field(default_factory=dict)
    # weekday "0".."6" -> next-day stats
    weekdays: dict[str, dict] = field(default_factory=dict)
    # vol regime "calm"|"normal"|"shock" -> next-day stats
    vol_regimes: dict[str, dict] = field(default_factory=dict)
    # drawdown decile "0".."9" -> next-day stats
    drawdowns: dict[str, dict] = field(default_factory=dict)
    # big-move follow-through: "up5"|"down5" (a >5% day) -> next-day stats
    big_moves: dict[str, dict] = field(default_factory=dict)
    # learned "comfort" volatility (EWMA of short vol) for regime_heat
    comfort_vol: float = 0.0

    def observe(self, feats: DayFeatures, next_ret: float) -> None:
        self.market_days += 1
        self.last_day = feats.day.isoformat()
        if not self.first_day:
            self.first_day = feats.day.isoformat()

        streak_key = str(max(-7, min(7, feats.streak)))
        _observe(self.streaks.setdefault(streak_key, _bucket_stats()), next_ret)
        _observe(self.months.setdefault(str(feats.day.month), _bucket_stats()), next_ret)
        _observe(self.weekdays.setdefault(str(feats.day.weekday()), _bucket_stats()), next_ret)
        regime = "shock" if feats.vol_shock > 0.5 else ("calm" if feats.vol_shock < 0.1 else "normal")
        _observe(self.vol_regimes.setdefault(regime, _bucket_stats()), next_ret)
        dd_key = str(min(9, int(feats.drawdown * 10)))
        _observe(self.drawdowns.setdefault(dd_key, _bucket_stats()), next_ret)
        if feats.ret1 > 0.05:
            _observe(self.big_moves.setdefault("up5", _bucket_stats()), next_ret)
        elif feats.ret1 < -0.05:
            _observe(self.big_moves.setdefault("down5", _bucket_stats()), next_ret)

        # EWMA comfort volatility (half-life ~90 market days).
        decay = 0.5 ** (1.0 / 90.0)
        self.comfort_vol = decay * self.comfort_vol + (1 - decay) * feats.vol_shock

    def regime_heat(self, feats: DayFeatures) -> float:
        """How far today's vol sits from the learned comfort zone, in [-1, 1]."""
        return max(-1.0, min(1.0, feats.vol_shock - self.comfort_vol))

    def edge(self, feats: DayFeatures) -> float:
        """Memory-implied next-day edge in [-1, 1] from the learned tables."""
        votes: list[float] = []
        for table, key in (
            (self.streaks, str(max(-7, min(7, feats.streak)))),
            (self.vol_regimes, "shock" if feats.vol_shock > 0.5 else ("calm" if feats.vol_shock < 0.1 else "normal")),
            (self.drawdowns, str(min(9, int(feats.drawdown * 10)))),
            (self.months, str(feats.day.month)),
        ):
            stats = table.get(key)
            if stats and stats["n"] >= 20:
                p_up = stats["up"] / stats["n"]
                votes.append(2.0 * (p_up - 0.5))
        if not votes:
            return 0.0
        return sum(votes) / len(votes)

    def summary(self) -> dict:
        return {
            "asset": self.asset,
            "days_walked": self.days_walked,
            "market_days": self.market_days,
            "pre_genesis_days": self.pre_genesis_days,
            "pre_market_days": self.pre_market_days,
            "gap_days": self.gap_days,
            "first_day": self.first_day,
            "last_day": self.last_day,
            "streaks": {k: _summ(v) for k, v in sorted(self.streaks.items(), key=lambda kv: int(kv[0]))},
            "vol_regimes": {k: _summ(v) for k, v in self.vol_regimes.items()},
            "drawdowns": {k: _summ(v) for k, v in sorted(self.drawdowns.items())},
            "big_moves": {k: _summ(v) for k, v in self.big_moves.items()},
            "comfort_vol": round(self.comfort_vol, 4),
        }

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "asset": self.asset,
            "days_walked": self.days_walked,
            "market_days": self.market_days,
            "pre_genesis_days": self.pre_genesis_days,
            "pre_market_days": self.pre_market_days,
            "gap_days": self.gap_days,
            "first_day": self.first_day,
            "last_day": self.last_day,
            "streaks": self.streaks,
            "months": self.months,
            "weekdays": self.weekdays,
            "vol_regimes": self.vol_regimes,
            "drawdowns": self.drawdowns,
            "big_moves": self.big_moves,
            "comfort_vol": self.comfort_vol,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PatternMemory:
        mem = cls(asset=str(data.get("asset", "")))
        for attr in (
            "days_walked",
            "market_days",
            "pre_genesis_days",
            "pre_market_days",
            "gap_days",
        ):
            setattr(mem, attr, int(data.get(attr, 0)))
        mem.first_day = str(data.get("first_day", ""))
        mem.last_day = str(data.get("last_day", ""))
        for attr in ("streaks", "months", "weekdays", "vol_regimes", "drawdowns", "big_moves"):
            setattr(mem, attr, {str(k): dict(v) for k, v in data.get(attr, {}).items()})
        mem.comfort_vol = float(data.get("comfort_vol", 0.0))
        return mem


# --- the trainer ---------------------------------------------------------------


@dataclass(frozen=True)
class TrainingReport:
    asset: str
    start: date
    end: date
    days_walked: int
    market_days: int
    pre_genesis_days: int
    pre_market_days: int
    gap_days: int
    adapter_updates: int
    hit_rate: float  # online (walk-forward) directional accuracy of the head
    worm_hit_rate: float  # directional accuracy of the connectome decisions
    worm_decisions: int

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "days_walked": self.days_walked,
            "market_days": self.market_days,
            "pre_genesis_days": self.pre_genesis_days,
            "pre_market_days": self.pre_market_days,
            "gap_days": self.gap_days,
            "adapter_updates": self.adapter_updates,
            "hit_rate": round(self.hit_rate, 4),
            "worm_hit_rate": round(self.worm_hit_rate, 4),
            "worm_decisions": self.worm_decisions,
        }


class DayByDayTrainer:
    """Walks the calendar and learns; persists everything it learns."""

    def __init__(
        self,
        asset: CryptoAsset,
        *,
        model_dir: str | Path = "data/crypto/models",
        lr: float = 0.02,
        seed: int = 7,
    ) -> None:
        self.asset = asset
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.lr = lr
        self.memory = PatternMemory(asset=asset.code)
        self.adapter = LowRankAdapter(N_FEATURES, 1, rank=4, alpha=8.0, seed=seed)
        self.worm = MarketWorm()
        self.load_state()

    # ------------------------------------------------------------- persistence
    def _paths(self) -> dict[str, Path]:
        stem = self.asset.code.lower()
        return {
            "memory": self.model_dir / f"{stem}_memory.json",
            "adapter": self.model_dir / f"{stem}_adapter.json",
            "worm": self.model_dir / f"{stem}_worm.json",
        }

    def load_state(self) -> bool:
        paths = self._paths()
        loaded = False
        if paths["memory"].exists():
            self.memory = PatternMemory.from_dict(json.loads(paths["memory"].read_text()))
            loaded = True
        if paths["adapter"].exists():
            try:
                self.adapter = LowRankAdapter.load(paths["adapter"])
            except (ValueError, KeyError, json.JSONDecodeError):
                pass
        if paths["worm"].exists():
            try:
                from aoa.connectome.engine import Connectome

                self.worm = MarketWorm(Connectome.from_dict(json.loads(paths["worm"].read_text())))
            except (ValueError, KeyError, json.JSONDecodeError):
                pass
        return loaded

    def save_state(self) -> None:
        paths = self._paths()
        paths["memory"].write_text(json.dumps(self.memory.to_dict()))
        self.adapter.save(paths["adapter"])
        paths["worm"].write_text(json.dumps(self.worm.connectome.to_dict()))

    # ---------------------------------------------------------------- predict
    def predict(self, feats: DayFeatures) -> float:
        """Predicted next-day return (fraction) from the low-rank head."""
        return self.adapter.delta(feats.vector())[0] * _RETURN_SCALE

    def combined_signal(self, feats: DayFeatures) -> tuple[str, float]:
        """Blend head prediction, worm motor output, and memory edge.

        Returns ``(action, conviction)`` where action is buy/sell/hold.
        """
        pred = self.predict(feats)
        decision = self.worm.decide(feats.stimulus(regime_heat=self.memory.regime_heat(feats)))
        edge = self.memory.edge(feats)

        score = 0.0
        score += max(-1.0, min(1.0, pred / _RETURN_SCALE))  # head vote
        score += (1.0 if decision.action == "buy" else -1.0 if decision.action == "sell" else 0.0) * decision.conviction
        score += 0.5 * edge
        conviction = min(1.0, abs(score) / 2.5)
        if score > 0.25:
            return "buy", conviction
        if score < -0.25:
            return "sell", conviction
        return "hold", 0.0

    # ---------------------------------------------------- strategy protocol
    def decide(self, feats: DayFeatures) -> tuple[str, float]:
        """Strategy-protocol alias for :meth:`combined_signal`."""
        return self.combined_signal(feats)

    def learn(self, feats: DayFeatures, next_ret: float, candle=None) -> None:
        """One online learning step (strategy protocol; ``candle`` unused)."""
        decision = self.worm.decide(feats.stimulus(regime_heat=self.memory.regime_heat(feats)))
        if decision.action != "hold":
            signed = next_ret if decision.action == "buy" else -next_ret
            self.worm.reinforce(max(-1.0, min(1.0, signed / _RETURN_SCALE)))
        self.memory.observe(feats, next_ret)
        target = max(-1.0, min(1.0, next_ret / _RETURN_SCALE))
        out = self.adapter.delta(feats.vector())[0]
        self.adapter.sgd_step(feats.vector(), [out - target], lr=self.lr, weight_decay=1e-4)

    # ------------------------------------------------------------------ train
    def train(
        self,
        candles: Sequence[DailyCandle],
        *,
        start: date = TRAINING_EPOCH,
        end: date | None = None,
        save: bool = True,
    ) -> TrainingReport:
        """Walk every calendar day in ``[start, end]`` and learn online."""
        idx_by_day = {c.day: i for i, c in enumerate(candles)}
        counts = {"pre-genesis": 0, "pre-market": 0, "gap": 0, "market": 0}
        days_walked = 0
        updates = 0
        head_hits = head_total = 0
        worm_hits = worm_total = 0
        last_day = start

        for cal in calendar_walk(self.asset, candles, start=start, end=end):
            days_walked += 1
            last_day = cal.day
            counts[cal.status] = counts.get(cal.status, 0) + 1
            if cal.status != "market" or cal.candle is None:
                continue
            idx = idx_by_day[cal.day]
            if idx + 1 >= len(candles):
                continue  # tomorrow unknown — nothing to learn from yet
            feats = extract_features(candles, idx)
            if feats is None:
                continue
            nxt = candles[idx + 1]
            if cal.candle.close <= 0:
                continue
            next_ret = nxt.close / cal.candle.close - 1.0

            # 1) Head prediction *before* learning (honest walk-forward score).
            pred = self.predict(feats)
            if abs(pred) > 1e-9:
                head_total += 1
                if pred * next_ret > 0:
                    head_hits += 1

            # 2) Worm decision + dopamine reinforcement.
            decision = self.worm.decide(
                feats.stimulus(regime_heat=self.memory.regime_heat(feats))
            )
            if decision.action != "hold":
                worm_total += 1
                signed = next_ret if decision.action == "buy" else -next_ret
                if signed > 0:
                    worm_hits += 1
                self.worm.reinforce(max(-1.0, min(1.0, signed / _RETURN_SCALE)))

            # 3) Pattern memory update.
            self.memory.observe(feats, next_ret)

            # 4) One SGD step on the head toward the realized return.
            target = max(-1.0, min(1.0, next_ret / _RETURN_SCALE))
            out = self.adapter.delta(feats.vector())[0]
            self.adapter.sgd_step(
                feats.vector(), [out - target], lr=self.lr, weight_decay=1e-4
            )
            updates += 1

        self.memory.days_walked += days_walked
        self.memory.pre_genesis_days += counts.get("pre-genesis", 0)
        self.memory.pre_market_days += counts.get("pre-market", 0)
        self.memory.gap_days += counts.get("gap", 0)
        if save:
            self.save_state()

        return TrainingReport(
            asset=self.asset.code,
            start=start,
            end=last_day,
            days_walked=days_walked,
            market_days=counts.get("market", 0),
            pre_genesis_days=counts.get("pre-genesis", 0),
            pre_market_days=counts.get("pre-market", 0),
            gap_days=counts.get("gap", 0),
            adapter_updates=updates,
            hit_rate=(head_hits / head_total) if head_total else 0.0,
            worm_hit_rate=(worm_hits / worm_total) if worm_total else 0.0,
            worm_decisions=worm_total,
        )
