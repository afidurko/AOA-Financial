"""Walk-forward backtest harness.

Replays the swarm's decisions through history **without lookahead**: at each
rebalance date the engine builds the decision from the bar slice *up to and
including* that date, then measures the realised forward return over the
holding ``horizon``. Aggregated metrics let you judge whether the engine has
edge and tune the agent weights on evidence rather than priors.

No lookahead guarantees:

* Each decision sees only ``bars[: i + 1]`` — the close on the decision date is
  the entry; the exit is ``bars[i + horizon]``.
* ``stored_sentiment`` and live fundamentals are **not** injected during the
  backtest (they are single latest-value snapshots and would leak the future);
  sentiment is derived purely from the in-slice momentum. Fundamentals can be
  supplied per-date by the caller if a point-in-time source exists.

By default ``step == horizon`` so holding periods are **non-overlapping**,
which makes the compounded equity curve and Sharpe well-defined.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..config import Config, TRADING_DAYS_PER_YEAR
from ..databases.store import MarketStore
from ..analysis import series as S
from ..swarm.decision import evaluate

_ACTION_DIR = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}


@dataclass
class BacktestTrade:
    date: str
    action: str
    conviction: float
    confidence: float
    target_weight: float
    fwd_return: float          # realised return over the horizon
    position: float            # signed exposure actually taken
    pnl: float                 # position * fwd_return

    def to_dict(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


@dataclass
class BacktestResult:
    ticker: str
    horizon: int
    step: int
    n_periods: int
    n_actionable: int
    years: float
    hit_rate: float                 # directional accuracy on actionable signals
    avg_signal_return: float        # mean directional return per actionable signal
    strategy_return: float          # compounded strategy return over the test
    buy_hold_return: float          # benchmark over the same window
    strategy_cagr: float            # annualised strategy return
    buy_hold_cagr: float            # annualised benchmark return
    excess_return: float            # strategy_cagr - buy_hold_cagr (annualised)
    sharpe: float                   # annualised, on per-period strategy returns
    max_drawdown: float             # of the strategy equity curve
    win_rate: float                 # fraction of non-zero positions with pnl>0
    trades: List[BacktestTrade] = field(default_factory=list)

    def to_dict(self, include_trades: bool = False) -> dict:
        d = {
            "ticker": self.ticker, "horizon": self.horizon, "step": self.step,
            "n_periods": self.n_periods, "n_actionable": self.n_actionable,
            "years": round(self.years, 2),
            "hit_rate": round(self.hit_rate, 4),
            "avg_signal_return": round(self.avg_signal_return, 6),
            "strategy_return": round(self.strategy_return, 4),
            "buy_hold_return": round(self.buy_hold_return, 4),
            "strategy_cagr": round(self.strategy_cagr, 4),
            "buy_hold_cagr": round(self.buy_hold_cagr, 4),
            "excess_return": round(self.excess_return, 4),
            "sharpe": round(self.sharpe, 3),
            "max_drawdown": round(self.max_drawdown, 4),
            "win_rate": round(self.win_rate, 4),
        }
        if include_trades:
            d["trades"] = [t.to_dict() for t in self.trades]
        return d


def _equity_metrics(period_returns: Sequence[float], horizon: int):
    """Sharpe and max drawdown from a list of per-period strategy returns."""
    if not period_returns:
        return 0.0, 0.0
    # Equity curve and its max drawdown.
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for r in period_returns:
        equity *= (1.0 + r)
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1.0)
    # Annualised Sharpe: periods per year = 252 / horizon.
    sd = S.stdev(period_returns)
    if sd == 0:
        return 0.0, mdd
    periods_per_year = TRADING_DAYS_PER_YEAR / horizon
    sharpe = (S.mean(period_returns) / sd) * math.sqrt(periods_per_year)
    return sharpe, mdd


def backtest_ticker(store: MarketStore, ticker: str, *,
                    horizon: int = 21,
                    step: Optional[int] = None,
                    warmup: int = 260,
                    config: Optional[Config] = None,
                    use_llm: bool = False,
                    use_fundamentals: bool = False,
                    max_position: float = 1.0) -> BacktestResult:
    """Walk-forward backtest of one ticker.

    ``position`` taken each period is the decision's ``conviction`` clamped to
    ``[-max_position, max_position]`` (longs and shorts), so the strategy
    return reflects both direction and conviction sizing.
    """
    config = config or Config()
    ticker = ticker.upper()
    bars = store.get_bars(ticker)
    step = step or horizon
    sec = store.get_security(ticker)
    sector = sec.sector if sec else "Unknown"
    # Point-in-time fundamentals are not generally available; opt-in only.
    fundamentals = store.latest_fundamentals(ticker) if use_fundamentals else None

    trades: List[BacktestTrade] = []
    period_returns: List[float] = []
    i = max(warmup, 60)
    while i + horizon < len(bars):
        sl = bars[: i + 1]
        decision = evaluate(ticker, sl, fundamentals=fundamentals,
                            stored_sentiment=None, sector=sector,
                            config=config, horizon=horizon, use_llm=use_llm)
        entry = bars[i].close
        exit_ = bars[i + horizon].close
        fwd = exit_ / entry - 1.0 if entry > 0 else 0.0
        position = max(-max_position, min(max_position, decision.conviction))
        pnl = position * fwd
        trades.append(BacktestTrade(
            date=bars[i].date, action=decision.action,
            conviction=decision.conviction, confidence=decision.confidence,
            target_weight=decision.target_weight, fwd_return=fwd,
            position=position, pnl=pnl))
        period_returns.append(pnl)
        i += step

    return _summarize(ticker, trades, period_returns, bars, horizon, step, warmup)


def _summarize(ticker, trades, period_returns, bars, horizon, step, warmup) -> BacktestResult:
    actionable = [t for t in trades if t.action != "HOLD"]
    hits = sum(1 for t in actionable
               if (_ACTION_DIR[t.action] > 0 and t.fwd_return > 0)
               or (_ACTION_DIR[t.action] < 0 and t.fwd_return < 0))
    hit_rate = hits / len(actionable) if actionable else 0.0
    avg_sig = (statistics.fmean(_ACTION_DIR[t.action] * t.fwd_return
                                for t in actionable) if actionable else 0.0)

    strat = 1.0
    for r in period_returns:
        strat *= (1.0 + r)
    strat_return = strat - 1.0

    # Buy & hold over the same tested window (entry of first to exit of last).
    bh_return = 0.0
    years = 0.0
    if trades:
        start_idx = max(warmup, 60)
        end_idx = min(len(bars) - 1, start_idx + step * (len(trades) - 1) + horizon)
        p0 = bars[start_idx].close
        p1 = bars[end_idx].close
        bh_return = p1 / p0 - 1.0 if p0 > 0 else 0.0
        years = (end_idx - start_idx) / TRADING_DAYS_PER_YEAR

    def _cagr(total: float) -> float:
        if years <= 0 or (1.0 + total) <= 0:
            return 0.0
        return (1.0 + total) ** (1.0 / years) - 1.0

    strat_cagr = _cagr(strat_return)
    bh_cagr = _cagr(bh_return)
    sharpe, mdd = _equity_metrics(period_returns, horizon)
    nonzero = [t for t in trades if t.position != 0]
    win_rate = (sum(1 for t in nonzero if t.pnl > 0) / len(nonzero)
                if nonzero else 0.0)

    return BacktestResult(
        ticker=ticker, horizon=horizon, step=step, n_periods=len(trades),
        n_actionable=len(actionable), years=years, hit_rate=hit_rate,
        avg_signal_return=avg_sig, strategy_return=strat_return,
        buy_hold_return=bh_return, strategy_cagr=strat_cagr,
        buy_hold_cagr=bh_cagr, excess_return=strat_cagr - bh_cagr,
        sharpe=sharpe, max_drawdown=mdd, win_rate=win_rate, trades=trades)


def backtest_universe(store: MarketStore, tickers: Sequence[str], *,
                      horizon: int = 21, step: Optional[int] = None,
                      config: Optional[Config] = None,
                      use_llm: bool = False) -> Dict[str, BacktestResult]:
    """Backtest each ticker; returns a mapping ticker -> result."""
    out: Dict[str, BacktestResult] = {}
    for t in tickers:
        try:
            out[t.upper()] = backtest_ticker(
                store, t, horizon=horizon, step=step, config=config,
                use_llm=use_llm)
        except ValueError:
            continue
    return out
