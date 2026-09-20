"""Walk-forward crypto backtester with mandatory pre-execution brackets.

The exit policy the user set is structural, not advisory: **every** entry must
carry a bracket — take-profit at **+32%** and stop-loss at **−26%** — computed
*before* the order executes. :class:`BracketPolicy.attach` is the only way to
build an executable entry, and :meth:`CryptoBacktester._execute_entry` refuses
an order without one, so no position can exist unprotected.

Fill model (conservative):

* Entries fill at the **next day's open** after a signal (no same-bar fills).
* Each day the stop is checked against the low *before* the target is checked
  against the high; when both are touched in one candle the stop wins.
* Exits fill exactly at the bracket price; fees apply on both sides.

This lane is offline research only — it never routes orders to a broker.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable

from aoa.crypto.assets import TRAINING_EPOCH, CryptoAsset
from aoa.crypto.history import DailyCandle
from aoa.crypto.training import DayByDayTrainer, DayFeatures, extract_features


@runtime_checkable
class DailyStrategy(Protocol):
    """Anything that can vote on a day and learn from its outcome."""

    def decide(self, feats: DayFeatures) -> tuple[str, float]: ...

    def learn(self, feats: DayFeatures, next_ret: float, candle: DailyCandle) -> None: ...

TAKE_PROFIT_PCT = 0.32
STOP_LOSS_PCT = 0.26


@dataclass(frozen=True)
class BracketPolicy:
    """Exit rules attached to every entry before it may execute."""

    take_profit_pct: float = TAKE_PROFIT_PCT
    stop_loss_pct: float = STOP_LOSS_PCT

    def __post_init__(self) -> None:
        if not 0 < self.take_profit_pct:
            raise ValueError("take_profit_pct must be positive")
        if not 0 < self.stop_loss_pct < 1:
            raise ValueError("stop_loss_pct must be in (0, 1)")

    def attach(self, entry_price: float) -> Bracket:
        """Compute the bracket for an entry — required before execution."""
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        return Bracket(
            entry_price=entry_price,
            take_profit=entry_price * (1.0 + self.take_profit_pct),
            stop_loss=entry_price * (1.0 - self.stop_loss_pct),
        )


@dataclass(frozen=True)
class Bracket:
    entry_price: float
    take_profit: float
    stop_loss: float


@dataclass(frozen=True)
class Trade:
    entry_day: date
    exit_day: date
    entry_price: float
    exit_price: float
    exit_reason: str  # "take-profit" | "stop-loss" | "signal" | "end-of-data"
    return_pct: float
    holding_days: int

    def to_dict(self) -> dict:
        return {
            "entry_day": self.entry_day.isoformat(),
            "exit_day": self.exit_day.isoformat(),
            "entry_price": round(self.entry_price, 6),
            "exit_price": round(self.exit_price, 6),
            "exit_reason": self.exit_reason,
            "return_pct": round(self.return_pct, 2),
            "holding_days": self.holding_days,
        }


@dataclass
class _OpenPosition:
    entry_day: date
    bracket: Bracket
    qty: float


@dataclass(frozen=True)
class BacktestResult:
    asset: str
    start: date
    end: date
    market_days: int
    trades: list[Trade]
    starting_cash: float
    ending_equity: float
    total_return_pct: float
    buy_hold_return_pct: float
    max_drawdown_pct: float
    win_rate: float
    take_profit_exits: int
    stop_loss_exits: int
    signal_exits: int
    fees_paid: float
    policy: BracketPolicy
    equity_curve: list[tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "market_days": self.market_days,
            "n_trades": len(self.trades),
            "starting_cash": self.starting_cash,
            "ending_equity": round(self.ending_equity, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "buy_hold_return_pct": round(self.buy_hold_return_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "win_rate": round(self.win_rate, 4),
            "take_profit_exits": self.take_profit_exits,
            "stop_loss_exits": self.stop_loss_exits,
            "signal_exits": self.signal_exits,
            "fees_paid": round(self.fees_paid, 2),
            "bracket": {
                "take_profit_pct": self.policy.take_profit_pct,
                "stop_loss_pct": self.policy.stop_loss_pct,
            },
        }

    def summary(self) -> str:
        return (
            f"{self.asset} — {self.start} → {self.end} ({self.market_days} market days)\n"
            f"  trades {len(self.trades)}  win rate {self.win_rate:.0%}  "
            f"exits: {self.take_profit_exits} take-profit / {self.stop_loss_exits} stop-loss / "
            f"{self.signal_exits} signal\n"
            f"  strategy {self.total_return_pct:+,.1f}%  vs buy&hold {self.buy_hold_return_pct:+,.1f}%  "
            f"max drawdown {self.max_drawdown_pct:.1f}%\n"
            f"  bracket: +{self.policy.take_profit_pct:.0%} target / "
            f"−{self.policy.stop_loss_pct:.0%} stop (attached before every entry)"
        )


class CryptoBacktester:
    """Day-by-day walk-forward backtest driven by any daily *strategy*.

    A strategy implements ``decide(feats) -> (action, conviction)`` and
    ``learn(feats, next_ret, candle)`` — both :class:`DayByDayTrainer` and
    :class:`~aoa.crypto.traders.HedgeEnsemble` qualify. The strategy is
    trained *incrementally inside the walk*: on day ``t`` it only uses state
    learned through day ``t-1`` (entries execute at the open of ``t+1``), so
    results are honest walk-forward, not in-sample.
    """

    def __init__(
        self,
        asset: CryptoAsset,
        *,
        policy: BracketPolicy | None = None,
        starting_cash: float = 10_000.0,
        fee_rate: float = 0.0025,
        warmup_days: int = 60,
    ) -> None:
        self.asset = asset
        self.policy = policy or BracketPolicy()
        self.starting_cash = starting_cash
        self.fee_rate = fee_rate
        self.warmup_days = warmup_days

    def run(
        self,
        candles: Sequence[DailyCandle],
        trainer: DayByDayTrainer | DailyStrategy,
        *,
        start: date = TRAINING_EPOCH,
        end: date | None = None,
        partner_closes: dict[date, float] | None = None,
    ) -> BacktestResult:
        window = [c for c in candles if c.day >= start and (end is None or c.day <= end)]
        if len(window) < self.warmup_days + 2:
            raise ValueError(
                f"not enough market data for {self.asset.code}: {len(window)} candles"
            )

        cash = self.starting_cash
        fees = 0.0
        position: _OpenPosition | None = None
        trades: list[Trade] = []
        curve: list[tuple[str, float]] = []
        peak_equity = cash
        max_dd = 0.0
        tp_exits = sl_exits = sig_exits = 0
        pending_action: str | None = None

        for i, candle in enumerate(window):
            # --- resolve any pending entry/exit at today's open -----------------
            if pending_action == "buy" and position is None and cash > 0:
                position, cash, fee = self._execute_entry(candle, cash)
                fees += fee
            elif pending_action == "sell" and position is not None:
                cash, fee = self._close(position, candle.open, candle.day, "signal", trades)
                fees += fee
                sig_exits += 1
                position = None
            pending_action = None

            # --- bracket exits, stop first (conservative) ------------------------
            # Gap realism: when the bar *opens* beyond a trigger, the fill is
            # the open (worse than the stop on a gap-down, better than the
            # target on a gap-up) — stops do not guarantee their price.
            if position is not None:
                br = position.bracket
                if candle.low <= br.stop_loss:
                    fill = min(br.stop_loss, candle.open)
                    cash, fee = self._close(position, fill, candle.day, "stop-loss", trades)
                    fees += fee
                    sl_exits += 1
                    position = None
                elif candle.high >= br.take_profit:
                    fill = max(br.take_profit, candle.open)
                    cash, fee = self._close(position, fill, candle.day, "take-profit", trades)
                    fees += fee
                    tp_exits += 1
                    position = None

            # --- pairs context (relative-value traders) ---------------------------
            if partner_closes is not None:
                partner = partner_closes.get(candle.day)
                update_pairs = getattr(trainer, "update_pairs", None)
                if partner and update_pairs is not None:
                    update_pairs(candle.close, partner)

            # --- learn today, decide for tomorrow --------------------------------
            feats = extract_features(window, i) if i + 1 < len(window) else None
            if feats is not None and i >= self.warmup_days:
                action, conviction = trainer.decide(feats)
                if action == "buy" and position is None and conviction > 0.1:
                    pending_action = "buy"
                elif action == "sell" and position is not None:
                    pending_action = "sell"
            # Incremental learning: teach the strategy this day's outcome so the
            # next decision uses everything up to (and including) today.
            if feats is not None and candle.close > 0:
                next_ret = window[i + 1].close / candle.close - 1.0
                trainer.learn(feats, next_ret, candle)

            equity = cash + (position.qty * candle.close if position else 0.0)
            peak_equity = max(peak_equity, equity)
            if peak_equity > 0:
                max_dd = max(max_dd, 1.0 - equity / peak_equity)
            curve.append((candle.day.isoformat(), round(equity, 2)))

        last = window[-1]
        if position is not None:
            cash, fee = self._close(position, last.close, last.day, "end-of-data", trades)
            fees += fee
            position = None
        ending = cash

        wins = sum(1 for t in trades if t.return_pct > 0)
        bh = (last.close / window[0].close - 1.0) * 100 if window[0].close > 0 else 0.0
        return BacktestResult(
            asset=self.asset.code,
            start=window[0].day,
            end=last.day,
            market_days=len(window),
            trades=trades,
            starting_cash=self.starting_cash,
            ending_equity=ending,
            total_return_pct=(ending / self.starting_cash - 1.0) * 100,
            buy_hold_return_pct=bh,
            max_drawdown_pct=max_dd * 100,
            win_rate=(wins / len(trades)) if trades else 0.0,
            take_profit_exits=tp_exits,
            stop_loss_exits=sl_exits,
            signal_exits=sig_exits,
            fees_paid=fees,
            policy=self.policy,
            equity_curve=curve,
        )

    # ------------------------------------------------------------------ helpers
    def _execute_entry(
        self, candle: DailyCandle, cash: float
    ) -> tuple[_OpenPosition, float, float]:
        """Execute a buy at the open — refuses to run without a bracket."""
        bracket = self.policy.attach(candle.open)  # bracket BEFORE execution
        if bracket.take_profit <= candle.open or bracket.stop_loss >= candle.open:
            raise RuntimeError("invalid bracket — refusing to execute entry")
        fee = cash * self.fee_rate
        qty = (cash - fee) / candle.open
        return _OpenPosition(entry_day=candle.day, bracket=bracket, qty=qty), 0.0, fee

    def _close(
        self,
        position: _OpenPosition,
        price: float,
        day: date,
        reason: str,
        trades: list[Trade],
    ) -> tuple[float, float]:
        gross = position.qty * price
        fee = gross * self.fee_rate
        entry = position.bracket.entry_price
        trades.append(
            Trade(
                entry_day=position.entry_day,
                exit_day=day,
                entry_price=entry,
                exit_price=price,
                exit_reason=reason,
                return_pct=(price / entry - 1.0) * 100,
                holding_days=(day - position.entry_day).days,
            )
        )
        return gross - fee, fee

