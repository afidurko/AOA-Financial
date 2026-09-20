"""Bar-level broker emulator that mirrors TradingView's strategy tester.

Fill model (matches Pine ``strategy()`` defaults unless configured otherwise):

* Orders created at a bar close fill at the **next bar's open**
  (``process_orders_on_close=false``). ``fill_on_close=True`` mirrors
  ``process_orders_on_close=true``.
* Stops / targets are evaluated **intrabar** using the broker emulator's price
  path assumption: open → nearer extreme → farther extreme → close. With
  ``conservative_intrabar=True`` a bar that touches both levels is always
  counted as a stop (worst case).
* Sizing is percent-of-equity at order time (``strategy.percent_of_equity``).
  Equities round down to whole shares; crypto is fractional.
* Commission is a percentage of notional per side; slippage is applied per
  fill either as ticks × tick size (when known) or as a percentage.

Everything is pure Python and deterministic. No orders. No broker.
"""

from __future__ import annotations

import itertools
import math
import random
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from aoa.brokerage.models import Bar
from aoa.tradingview.presets import Preset
from aoa.tradingview.rules import build_strategy, in_session

# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EmulatorConfig:
    initial_capital: float = 100_000.0
    fill_on_close: bool = False
    conservative_intrabar: bool = False
    tick_size: float | None = None
    fractional_equity: bool = False


@dataclass
class Trade:
    side: str  # "long" | "short"
    entry_index: int
    entry_time: datetime
    entry_price: float
    qty: float
    exit_index: int = -1
    exit_time: datetime | None = None
    exit_price: float = 0.0
    exit_reason: str = ""
    commission: float = 0.0
    stop: float | None = None
    target: float | None = None

    @property
    def is_open(self) -> bool:
        return self.exit_index < 0

    @property
    def direction(self) -> float:
        return 1.0 if self.side == "long" else -1.0

    @property
    def pnl(self) -> float:
        if self.is_open:
            return 0.0
        return (self.exit_price - self.entry_price) * self.qty * self.direction - self.commission

    @property
    def pnl_pct(self) -> float:
        notional = self.entry_price * self.qty
        return (self.pnl / notional) * 100.0 if notional else 0.0

    @property
    def bars_held(self) -> int:
        return (self.exit_index - self.entry_index) if not self.is_open else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "entry_index": self.entry_index,
            "entry_time": self.entry_time.isoformat(),
            "entry_price": round(self.entry_price, 8),
            "qty": round(self.qty, 8),
            "exit_index": self.exit_index,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": round(self.exit_price, 8),
            "exit_reason": self.exit_reason,
            "commission": round(self.commission, 6),
            "pnl": round(self.pnl, 6),
            "pnl_pct": round(self.pnl_pct, 4),
            "bars_held": self.bars_held,
        }


@dataclass
class BacktestResult:
    preset_name: str
    symbol: str
    timeframe: str
    market: str
    params: dict[str, Any]
    n_bars: int
    start: datetime | None
    end: datetime | None
    trades: list[Trade]
    equity_curve: list[float]
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_trades: bool = False) -> dict[str, Any]:
        out = {
            "preset": self.preset_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "market": self.market,
            "params": dict(self.params),
            "n_bars": self.n_bars,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "metrics": dict(self.metrics),
        }
        if include_trades:
            out["trades"] = [t.to_dict() for t in self.trades]
        return out


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


def _slip(price: float, preset: Preset, cfg: EmulatorConfig, *, adverse_up: bool) -> float:
    """Apply slippage against the trader (buys fill higher, sells fill lower)."""
    if cfg.tick_size:
        delta = preset.costs.slippage_ticks * cfg.tick_size
    else:
        delta = price * preset.costs.slippage_pct / 100.0
    return price + delta if adverse_up else max(price - delta, 0.0)


def _intrabar_hits(bar: Bar, stop: float | None, target: float | None, side: str, cfg: EmulatorConfig) -> tuple[str, float] | None:
    """Return (reason, price) if a stop or target fills within ``bar``."""
    if side == "long":
        stop_hit = stop is not None and bar.low <= stop
        target_hit = target is not None and bar.high >= target
    else:
        stop_hit = stop is not None and bar.high >= stop
        target_hit = target is not None and bar.low <= target
    if not stop_hit and not target_hit:
        return None
    if stop_hit and not target_hit:
        return "stop", _gap_fill(bar, stop, side, is_stop=True)  # type: ignore[arg-type]
    if target_hit and not stop_hit:
        return "target", target  # type: ignore[return-value]
    if cfg.conservative_intrabar:
        return "stop", _gap_fill(bar, stop, side, is_stop=True)  # type: ignore[arg-type]
    # TradingView path assumption: open → nearer extreme first.
    to_high = abs(bar.high - bar.open)
    to_low = abs(bar.open - bar.low)
    low_first = to_low <= to_high
    if side == "long":
        if low_first:
            return "stop", _gap_fill(bar, stop, side, is_stop=True)  # type: ignore[arg-type]
        return "target", target  # type: ignore[return-value]
    if low_first:
        return "target", target  # type: ignore[return-value]
    return "stop", _gap_fill(bar, stop, side, is_stop=True)  # type: ignore[arg-type]


def _gap_fill(bar: Bar, level: float, side: str, *, is_stop: bool) -> float:
    """Stops that gap through fill at the open (worse than the level)."""
    if side == "long":
        return min(level, bar.open) if is_stop else level
    return max(level, bar.open) if is_stop else level


def run_backtest(
    bars: list[Bar],
    preset: Preset,
    *,
    symbol: str = "SYMBOL",
    cfg: EmulatorConfig | None = None,
    params: dict[str, Any] | None = None,
    start_index: int = 0,
    fundamentals_ok: bool = True,
) -> BacktestResult:
    """Replay ``bars`` through ``preset``'s rules with TradingView fill semantics."""
    cfg = cfg or EmulatorConfig()
    if params:
        preset = preset.with_params(**params)
    strat = build_strategy(preset, fundamentals_ok=fundamentals_ok)
    risk = preset.risk
    costs = preset.costs
    tf_seconds = preset.tf.seconds
    market = preset.market
    fractional = market == "crypto" or cfg.fractional_equity

    equity = cfg.initial_capital
    cash = equity
    equity_curve: list[float] = []
    trades: list[Trade] = []
    open_trade: Trade | None = None
    pending: dict[str, Any] | None = None  # {"action": "enter"|"exit", "side", "atr", "reason"}
    entries_today: dict[Any, int] = {}
    first_trade_index = max(start_index, strat.warmup)

    def _commission(notional: float) -> float:
        return abs(notional) * costs.commission_pct / 100.0

    def _close_trade(t: Trade, idx: int, price: float, reason: str, ts: datetime) -> None:
        nonlocal cash, open_trade
        adverse_up = t.side == "short"  # covering a short = buying → slips up
        fill = _slip(price, preset, cfg, adverse_up=adverse_up)
        exit_comm = _commission(fill * t.qty)
        t.exit_index = idx
        t.exit_time = ts
        t.exit_price = fill
        t.exit_reason = reason
        t.commission += exit_comm
        # long: receive proceeds; short: pay to cover (entry proceeds were credited).
        cash += fill * t.qty * t.direction - exit_comm
        open_trade = None

    def _open_trade(side: str, idx: int, price: float, atr: float | None, ts: datetime) -> None:
        nonlocal cash, open_trade
        adverse_up = side == "long"
        fill = _slip(price, preset, cfg, adverse_up=adverse_up)
        if fill <= 0:
            return
        notional = equity * risk.qty_pct_equity / 100.0
        qty = notional / fill
        if not fractional:
            qty = float(math.floor(qty))
        if qty <= 0:
            return
        comm = _commission(fill * qty)
        t = Trade(side=side, entry_index=idx, entry_time=ts, entry_price=fill, qty=qty, commission=comm)
        direction = t.direction
        if atr and risk.stop_atr > 0:
            t.stop = fill - direction * risk.stop_atr * atr
        if atr and risk.target_atr > 0:
            t.target = fill + direction * risk.target_atr * atr
        # The trailing stop (if any) starts ratcheting on the first close after entry,
        # exactly like the generated Pine script.
        cash -= fill * qty * direction + comm
        open_trade = t
        trades.append(t)

    def _session_key(ts: datetime) -> Any:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.date()

    for i, bar in enumerate(bars):
        ts = bar.timestamp
        # --- 1. pending orders fill at this bar's open ---------------------------
        if pending is not None and not cfg.fill_on_close:
            if pending["action"] == "exit" and open_trade is not None:
                _close_trade(open_trade, i, bar.open, pending["reason"], ts)
            elif pending["action"] == "enter" and open_trade is None:
                _open_trade(pending["side"], i, bar.open, pending["atr"], ts)
                entries_today[_session_key(ts)] = entries_today.get(_session_key(ts), 0) + 1
            pending = None
        # --- 2. intrabar protective exits ---------------------------------------
        if open_trade is not None:
            hit = _intrabar_hits(bar, open_trade.stop, open_trade.target, open_trade.side, cfg)
            if hit is not None:
                reason, price = hit
                _close_trade(open_trade, i, price, reason, ts)
        # --- 3. strategy logic at the close ------------------------------------
        sig = strat.on_bar(bar)
        session_ok = in_session(ts, risk.session, market)
        last_session_bar = (
            risk.session is not None
            and session_ok
            and not in_session(ts + timedelta(seconds=tf_seconds), risk.session, market)
        )
        if open_trade is not None:
            t = open_trade
            # trailing stop ratchets on the close
            if risk.trail_atr > 0 and sig.atr:
                candidate = bar.close - t.direction * risk.trail_atr * sig.atr
                if t.side == "long":
                    if t.stop is None or candidate > t.stop:
                        t.stop = candidate
                elif t.stop is None or candidate < t.stop:
                    t.stop = candidate
            time_stop = risk.max_bars_in_trade > 0 and (i - t.entry_index) >= risk.max_bars_in_trade
            signal_exit = (t.side == "long" and sig.exit_long) or (t.side == "short" and sig.exit_short)
            reason = None
            if last_session_bar or (risk.session and not session_ok):
                reason = "session_end"
            elif time_stop:
                reason = "time"
            elif signal_exit:
                reason = "signal"
            if reason:
                if cfg.fill_on_close or reason == "session_end":
                    _close_trade(t, i, bar.close, reason, ts)
                else:
                    pending = {"action": "exit", "reason": reason}
        if open_trade is None and pending is None and i >= first_trade_index and sig.ready:
            side = "long" if sig.long_entry else ("short" if sig.short_entry else None)
            day = _session_key(ts)
            cap_ok = risk.max_trades_per_day <= 0 or entries_today.get(day, 0) < risk.max_trades_per_day
            if side and session_ok and not last_session_bar and cap_ok:
                if cfg.fill_on_close:
                    _open_trade(side, i, bar.close, sig.atr, ts)
                    entries_today[day] = entries_today.get(day, 0) + 1
                else:
                    pending = {"action": "enter", "side": side, "atr": sig.atr}
        # --- 4. mark to market ---------------------------------------------------
        if open_trade is not None:
            # long: cash + market value; short: cash (incl. entry proceeds) - cost to cover
            equity = cash + bar.close * open_trade.qty * open_trade.direction
        else:
            equity = cash
        equity_curve.append(equity)

    # force-close any open trade at the last close so metrics are complete
    if open_trade is not None and bars:
        last = bars[-1]
        _close_trade(open_trade, len(bars) - 1, last.close, "end", last.timestamp)
        equity = cash
        equity_curve[-1] = equity

    result = BacktestResult(
        preset_name=preset.name,
        symbol=symbol,
        timeframe=preset.timeframe,
        market=market,
        params=dict(preset.params),
        n_bars=len(bars),
        start=bars[0].timestamp if bars else None,
        end=bars[-1].timestamp if bars else None,
        trades=trades,
        equity_curve=equity_curve,
    )
    result.metrics = compute_metrics(result, preset, cfg, bars, start_index=first_trade_index)
    return result


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def max_drawdown_pct(curve: list[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            dd = (v / peak - 1.0) * 100.0
            worst = min(worst, dd)
    return round(worst, 4)


def _bar_returns(curve: list[float]) -> list[float]:
    out = []
    for a, b in zip(curve, curve[1:], strict=False):
        out.append(b / a - 1.0 if a > 0 else 0.0)
    return out


def compute_metrics(
    result: BacktestResult,
    preset: Preset,
    cfg: EmulatorConfig,
    bars: list[Bar],
    *,
    start_index: int = 0,
) -> dict[str, Any]:
    closed = [t for t in result.trades if not t.is_open]
    curve = result.equity_curve
    initial = cfg.initial_capital
    final = curve[-1] if curve else initial
    net = final - initial
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    pnl_pcts = [t.pnl_pct for t in closed]
    bars_per_year = preset.tf.bars_per_year(preset.market)
    n_eval = max(len(curve) - start_index, 1)
    years = n_eval / bars_per_year if bars_per_year else 0.0
    rets = _bar_returns(curve[start_index:]) if len(curve) > start_index + 1 else []
    sharpe = sortino = 0.0
    if len(rets) > 2:
        mu = statistics.fmean(rets)
        sd = statistics.pstdev(rets)
        if sd > 0:
            sharpe = mu / sd * math.sqrt(bars_per_year)
        downside = [min(r, 0.0) for r in rets]
        dsd = math.sqrt(sum(d * d for d in downside) / len(downside))
        if dsd > 0:
            sortino = mu / dsd * math.sqrt(bars_per_year)
    cagr = 0.0
    if years > 0 and initial > 0 and final > 0:
        cagr = ((final / initial) ** (1.0 / years) - 1.0) * 100.0
    bh = 0.0
    if bars and len(bars) > start_index and bars[start_index].close > 0:
        bh = (bars[-1].close / bars[start_index].close - 1.0) * 100.0
    bars_in_pos = sum(t.bars_held for t in closed)
    sqn = 0.0
    if len(pnl_pcts) > 1:
        sd = statistics.pstdev(pnl_pcts)
        if sd > 0:
            sqn = math.sqrt(len(pnl_pcts)) * statistics.fmean(pnl_pcts) / sd
    reasons: dict[str, int] = {}
    for t in closed:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    return {
        "net_profit": round(net, 2),
        "net_profit_pct": round(net / initial * 100.0, 4) if initial else 0.0,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
        "total_trades": len(closed),
        "win_rate_pct": round(len(wins) / len(closed) * 100.0, 2) if closed else 0.0,
        "avg_trade_pct": round(statistics.fmean(pnl_pcts), 4) if pnl_pcts else 0.0,
        "avg_win_pct": round(statistics.fmean([t.pnl_pct for t in wins]), 4) if wins else 0.0,
        "avg_loss_pct": round(statistics.fmean([t.pnl_pct for t in losses]), 4) if losses else 0.0,
        "largest_win_pct": round(max(pnl_pcts), 4) if pnl_pcts else 0.0,
        "largest_loss_pct": round(min(pnl_pcts), 4) if pnl_pcts else 0.0,
        "expectancy_pct": round(statistics.fmean(pnl_pcts), 4) if pnl_pcts else 0.0,
        "max_drawdown_pct": max_drawdown_pct(curve[start_index:]) if curve else 0.0,
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "sqn": round(sqn, 4),
        "cagr_pct": round(cagr, 4),
        "buy_hold_return_pct": round(bh, 4),
        "exposure_pct": round(bars_in_pos / n_eval * 100.0, 2),
        "avg_bars_in_trade": round(bars_in_pos / len(closed), 2) if closed else 0.0,
        "trades_per_year": round(len(closed) / years, 2) if years > 0 else 0.0,
        "commission_paid": round(sum(t.commission for t in closed), 2),
        "exit_reasons": reasons,
        "years": round(years, 3),
        "bars_evaluated": n_eval,
    }


# --------------------------------------------------------------------------- #
# Research helpers: sweeps, walk-forward, Monte-Carlo
# --------------------------------------------------------------------------- #

OBJECTIVES = ("sqn", "profit_factor", "sharpe", "net_profit_pct", "expectancy_pct")


def objective_value(metrics: dict[str, Any], objective: str, *, min_trades: int = 5) -> float:
    if metrics.get("total_trades", 0) < min_trades:
        return -math.inf
    v = metrics.get(objective, 0.0)
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return -math.inf if v is None or math.isnan(v) else 1e9
    return float(v)


def param_grid(preset: Preset, grid: dict[str, tuple[Any, ...]] | None = None) -> list[dict[str, Any]]:
    grid = grid or preset.tunable
    if not grid:
        return [dict()]
    keys = list(grid)
    combos = []
    for values in itertools.product(*(grid[k] for k in keys)):
        combos.append(dict(zip(keys, values, strict=True)))
    return combos


def sweep(
    bars: list[Bar],
    preset: Preset,
    *,
    symbol: str = "SYMBOL",
    grid: dict[str, tuple[Any, ...]] | None = None,
    cfg: EmulatorConfig | None = None,
    objective: str = "sqn",
    min_trades: int = 5,
    start_index: int = 0,
    fundamentals_ok: bool = True,
) -> list[dict[str, Any]]:
    """Grid-search ``preset.tunable`` (or ``grid``) and rank by ``objective``."""
    rows = []
    for params in param_grid(preset, grid):
        res = run_backtest(
            bars, preset, symbol=symbol, cfg=cfg, params=params, start_index=start_index, fundamentals_ok=fundamentals_ok
        )
        rows.append(
            {
                "params": params,
                "objective": objective,
                "score": objective_value(res.metrics, objective, min_trades=min_trades),
                "metrics": res.metrics,
            }
        )
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


@dataclass
class WalkForwardResult:
    preset_name: str
    symbol: str
    folds: list[dict[str, Any]]
    oos_equity: list[float]
    oos_metrics: dict[str, Any]
    is_metrics_mean: dict[str, float]
    oos_is_ratio: float | None
    objective: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset_name,
            "symbol": self.symbol,
            "objective": self.objective,
            "folds": self.folds,
            "oos_metrics": self.oos_metrics,
            "is_metrics_mean": self.is_metrics_mean,
            "oos_is_ratio": self.oos_is_ratio,
        }


def walk_forward(
    bars: list[Bar],
    preset: Preset,
    *,
    symbol: str = "SYMBOL",
    folds: int = 4,
    grid: dict[str, tuple[Any, ...]] | None = None,
    cfg: EmulatorConfig | None = None,
    objective: str = "sqn",
    min_trades: int = 5,
    anchored: bool = False,
    fundamentals_ok: bool = True,
) -> WalkForwardResult:
    """Anchored or rolling walk-forward optimisation with strict out-of-sample tests.

    The series is cut into ``folds + 1`` contiguous segments. For fold *k* the
    parameters are chosen on segments ``[0..k)`` (anchored) or ``[k-1]``
    (rolling) and then evaluated on segment ``k`` only. Out-of-sample runs are
    warmed up on in-sample bars but no entry before the OOS boundary is counted.
    """
    cfg = cfg or EmulatorConfig()
    n = len(bars)
    seg = n // (folds + 1)
    if seg < 20:
        raise ValueError("not enough bars for the requested number of folds")
    fold_rows: list[dict[str, Any]] = []
    stitched: list[float] = []
    equity_scale = 1.0
    is_scores: dict[str, list[float]] = {}
    for k in range(1, folds + 1):
        is_start = 0 if anchored else (k - 1) * seg
        is_end = k * seg
        oos_end = n if k == folds else (k + 1) * seg
        is_bars = bars[is_start:is_end]
        ranked = sweep(
            is_bars, preset, symbol=symbol, grid=grid, cfg=cfg, objective=objective, min_trades=min_trades,
            fundamentals_ok=fundamentals_ok,
        )
        best = ranked[0] if ranked else {"params": {}, "metrics": {}, "score": -math.inf}
        # Warm the OOS run on in-sample history so indicators are live at the boundary.
        warm = build_strategy(preset.with_params(**best["params"])).warmup * 3
        window_start = max(is_end - warm, 0)
        oos_res = run_backtest(
            bars[window_start:oos_end],
            preset,
            symbol=symbol,
            cfg=cfg,
            params=best["params"],
            start_index=is_end - window_start,
            fundamentals_ok=fundamentals_ok,
        )
        oos_curve = oos_res.equity_curve[is_end - window_start :]
        base = oos_curve[0] if oos_curve else cfg.initial_capital
        for v in oos_curve:
            stitched.append(equity_scale * (v / base if base else 1.0) * cfg.initial_capital)
        if oos_curve and base:
            equity_scale *= oos_curve[-1] / base
        for key in ("sqn", "profit_factor", "sharpe", "net_profit_pct", "expectancy_pct"):
            v = best["metrics"].get(key)
            if isinstance(v, int | float) and math.isfinite(v):
                is_scores.setdefault(key, []).append(float(v))
        fold_rows.append(
            {
                "fold": k,
                "is_range": [is_start, is_end],
                "oos_range": [is_end, oos_end],
                "best_params": best["params"],
                "is_score": best["score"] if math.isfinite(best["score"]) else None,
                "is_metrics": best["metrics"],
                "oos_metrics": oos_res.metrics,
            }
        )
    oos_metrics = {
        "net_profit_pct": round((stitched[-1] / cfg.initial_capital - 1.0) * 100.0, 4) if stitched else 0.0,
        "max_drawdown_pct": max_drawdown_pct(stitched) if stitched else 0.0,
        "total_trades": sum(int(f["oos_metrics"].get("total_trades", 0)) for f in fold_rows),
        "folds_profitable": sum(1 for f in fold_rows if f["oos_metrics"].get("net_profit", 0) > 0),
        "mean_oos_sqn": round(statistics.fmean([f["oos_metrics"].get("sqn", 0.0) for f in fold_rows]), 4) if fold_rows else 0.0,
        "mean_oos_profit_factor": round(
            statistics.fmean(
                [min(f["oos_metrics"].get("profit_factor", 0.0), 10.0) for f in fold_rows]
            ),
            4,
        )
        if fold_rows
        else 0.0,
    }
    is_mean = {k: round(statistics.fmean(v), 4) for k, v in is_scores.items() if v}
    ratio = None
    is_obj = is_mean.get(objective)
    oos_obj = oos_metrics.get("mean_oos_sqn") if objective == "sqn" else None
    if objective == "profit_factor":
        oos_obj = oos_metrics.get("mean_oos_profit_factor")
    # Only meaningful when the in-sample objective was positive (a "good" fit).
    if is_obj is not None and is_obj > 0 and oos_obj is not None:
        ratio = round(oos_obj / is_obj, 4)
    return WalkForwardResult(
        preset_name=preset.name,
        symbol=symbol,
        folds=fold_rows,
        oos_equity=stitched,
        oos_metrics=oos_metrics,
        is_metrics_mean=is_mean,
        oos_is_ratio=ratio,
        objective=objective,
    )


def monte_carlo_trades(
    trades: list[Trade],
    *,
    n_paths: int = 1000,
    seed: int = 7,
    ruin_dd_pct: float = 20.0,
    position_fraction: float | None = None,
) -> dict[str, Any]:
    """Shuffle realised trade returns to estimate drawdown / ending-equity spread.

    ``position_fraction`` scales each trade's percent return by the fraction of
    equity deployed (defaults to the preset sizing implied by the trades).
    """
    pnl_pcts = [t.pnl_pct / 100.0 for t in trades if not t.is_open]
    if len(pnl_pcts) < 2:
        return {"ok": False, "reason": "need at least two closed trades", "n_trades": len(pnl_pcts)}
    frac = position_fraction if position_fraction is not None else 1.0
    rng = random.Random(seed)
    finals: list[float] = []
    dds: list[float] = []
    ruined = 0
    for _ in range(n_paths):
        seq = pnl_pcts[:]
        rng.shuffle(seq)
        eq = 1.0
        peak = 1.0
        worst = 0.0
        for r in seq:
            eq *= 1.0 + r * frac
            peak = max(peak, eq)
            worst = min(worst, (eq / peak - 1.0) * 100.0)
        finals.append((eq - 1.0) * 100.0)
        dds.append(worst)
        if worst <= -ruin_dd_pct:
            ruined += 1
    dds.sort()

    def pct(xs: list[float], q: float) -> float:
        idx = min(int(q * (len(xs) - 1)), len(xs) - 1)
        return round(xs[idx], 4)

    # The compounded final return is order-invariant; only the path (drawdown) varies.
    return {
        "ok": True,
        "n_trades": len(pnl_pcts),
        "n_paths": n_paths,
        "final_return_pct": round(finals[0], 4),
        "max_drawdown_pct": {"p5": pct(dds, 0.05), "p50": pct(dds, 0.5), "p95": pct(dds, 0.95)},
        "p_drawdown_exceeds": {f"{ruin_dd_pct:g}pct": round(ruined / n_paths, 4)},
    }
