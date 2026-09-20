"""First-passage survival statistics for the 32/26 bracket.

Distilled from the account's survival-analysis forks (``lifelines``,
``scikit-survival``): instead of modeling *time to death*, we model each
hypothetical entry's race between two absorbing barriers — the **+32%
take-profit** and the **−26% stop-loss** — and estimate, per market regime,
which side history hit first.

Every market day the tracker opens a *virtual* bracket at that day's close.
As later candles arrive, each pending virtual entry is resolved the moment its
high crosses the target or its low crosses the stop (stop checked first, same
conservative order as the backtester), or **censored** (survival-analysis
vocabulary for "observation ended before the event") at the horizon. Outcomes
accumulate per regime key — volatility regime × drawdown bucket — and the
resulting conditional win odds gate live entries: when history says entries
from this regime hit the stop first far more often than the target, the gate
closes.

Fully online: a virtual entry opened on day *t* only ever consumes candles
after *t*, so the statistics are usable inside a walk-forward loop with no
lookahead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aoa.crypto.history import DailyCandle
from aoa.crypto.training import DayFeatures


def regime_key(feats: DayFeatures) -> str:
    """Regime bucket: volatility regime × drawdown quartile."""
    vol = "shock" if feats.vol_shock > 0.5 else ("calm" if feats.vol_shock < 0.1 else "normal")
    dd = min(3, int(feats.drawdown * 4))
    return f"{vol}:dd{dd}"


@dataclass
class _Pending:
    key: str
    target: float
    stop: float
    age: int = 0


@dataclass
class BracketSurvival:
    """Online first-passage tracker for a fixed bracket geometry."""

    take_profit_pct: float = 0.32
    stop_loss_pct: float = 0.26
    horizon_days: int = 365
    # regime key -> {"tp": hits, "sl": hits, "censored": count}
    outcomes: dict[str, dict[str, int]] = field(default_factory=dict)
    _pending: list[_Pending] = field(default_factory=list)

    # ------------------------------------------------------------------ updates
    def open_virtual(self, feats: DayFeatures, close: float) -> None:
        """Register a hypothetical entry at ``close`` under today's regime."""
        if close <= 0:
            return
        self._pending.append(
            _Pending(
                key=regime_key(feats),
                target=close * (1.0 + self.take_profit_pct),
                stop=close * (1.0 - self.stop_loss_pct),
            )
        )

    def observe_candle(self, candle: DailyCandle) -> None:
        """Resolve pending virtual entries against a new candle."""
        still: list[_Pending] = []
        for p in self._pending:
            p.age += 1
            if candle.low <= p.stop:  # stop first — conservative, as in backtest
                self._record(p.key, "sl")
            elif candle.high >= p.target:
                self._record(p.key, "tp")
            elif p.age >= self.horizon_days:
                self._record(p.key, "censored")
            else:
                still.append(p)
        self._pending = still

    def _record(self, key: str, outcome: str) -> None:
        stats = self.outcomes.setdefault(key, {"tp": 0, "sl": 0, "censored": 0})
        stats[outcome] += 1

    # ------------------------------------------------------------------ queries
    def win_odds(self, feats: DayFeatures) -> tuple[float, int]:
        """``(P(target before stop), resolved_n)`` for today's regime.

        Censored entries are excluded from the odds (the race never finished),
        mirroring how Kaplan-Meier treats censored observations. Returns
        ``(0.5, 0)`` when the regime has no resolved history yet.
        """
        stats = self.outcomes.get(regime_key(feats))
        if not stats:
            return 0.5, 0
        resolved = stats["tp"] + stats["sl"]
        if resolved == 0:
            return 0.5, 0
        return stats["tp"] / resolved, resolved

    def allows(self, feats: DayFeatures, *, min_odds: float = 0.45, min_n: int = 12) -> bool:
        """Gate: block entries only when ample history says the stop wins.

        With fewer than ``min_n`` resolved races the gate stays open (no
        evidence — no veto), so the gate can never deadlock early training.
        """
        odds, n = self.win_odds(feats)
        return n < min_n or odds >= min_odds

    def summary(self) -> dict:
        out: dict[str, dict] = {}
        for key, stats in sorted(self.outcomes.items()):
            resolved = stats["tp"] + stats["sl"]
            out[key] = {
                "tp": stats["tp"],
                "sl": stats["sl"],
                "censored": stats["censored"],
                "p_tp_first": round(stats["tp"] / resolved, 4) if resolved else None,
            }
        return out

    # ------------------------------------------------------------ (de)serialize
    def to_dict(self) -> dict:
        return {
            "take_profit_pct": self.take_profit_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "horizon_days": self.horizon_days,
            "outcomes": self.outcomes,
            "pending": [
                {"key": p.key, "target": p.target, "stop": p.stop, "age": p.age}
                for p in self._pending
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BracketSurvival:
        tracker = cls(
            take_profit_pct=float(data.get("take_profit_pct", 0.32)),
            stop_loss_pct=float(data.get("stop_loss_pct", 0.26)),
            horizon_days=int(data.get("horizon_days", 365)),
        )
        tracker.outcomes = {
            str(k): {kk: int(vv) for kk, vv in v.items()} for k, v in data.get("outcomes", {}).items()
        }
        tracker._pending = [
            _Pending(
                key=str(p["key"]),
                target=float(p["target"]),
                stop=float(p["stop"]),
                age=int(p.get("age", 0)),
            )
            for p in data.get("pending", [])
        ]
        return tracker
