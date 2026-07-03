"""Monte-Carlo market simulator.

Fits a return process to a real bar history, then generates many forward price
paths to estimate the distribution of outcomes. Two engines, plus deterministic
scenario replay:

* **GBM** — geometric Brownian motion using the drift/vol estimated from history.
  Smooth, parametric, fast; assumes log-normal returns.
* **Block bootstrap** — resamples *contiguous blocks* of the actual historical
  returns. Non-parametric: it preserves fat tails and short-run autocorrelation
  that GBM throws away.
* **Scenario replay / stress test** — apply a :class:`~aoa.simulation.scenarios.Scenario`
  (a 2008, a COVID crash, a real extracted window) to the current price.

Pure-Python ``random`` (seedable for reproducibility); no numpy.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from aoa.brokerage.models import Bar
from aoa.simulation.scenarios import Scenario
from aoa.simulation.trends import TRADING_DAYS, log_returns

_PERCENTILES = (5, 10, 25, 50, 75, 90, 95)


def _percentile(sorted_vals: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile of an already-sorted sequence."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100) * (len(sorted_vals) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_vals[lo]
    frac = rank - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


@dataclass(frozen=True)
class SimulationConfig:
    method: str = "gbm"  # "gbm" | "bootstrap"
    horizon: int = 21  # bars to project forward (~1 trading month)
    n_paths: int = 1000
    block_size: int = 5  # bootstrap block length
    seed: int | None = None
    # Recency weighting for parameter estimation. When set, returns decay with
    # this half-life (in bars) so the model adapts to the *current* regime
    # instead of weighting a year-old crash the same as yesterday. None == equal
    # weight (stationary estimate).
    ewma_halflife: int | None = None


@dataclass(frozen=True)
class SimulationResult:
    symbol: str
    method: str
    start_price: float
    horizon: int
    n_paths: int
    mean_ending: float
    median_ending: float
    std_ending: float
    expected_return_pct: float
    prob_profit: float
    prob_loss: float
    var_95_pct: float  # 5th-percentile return (a loss threshold; negative)
    cvar_95_pct: float  # mean return in the worst 5% of paths (negative)
    best_ending: float
    worst_ending: float
    ending_percentiles: dict[int, float]  # price levels by percentile
    # A small sample of full paths, for plotting/inspection (not all n_paths).
    sample_paths: list[list[float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "method": self.method,
            "start_price": round(self.start_price, 4),
            "horizon": self.horizon,
            "n_paths": self.n_paths,
            "mean_ending": round(self.mean_ending, 4),
            "median_ending": round(self.median_ending, 4),
            "std_ending": round(self.std_ending, 4),
            "expected_return_pct": self.expected_return_pct,
            "prob_profit": self.prob_profit,
            "prob_loss": self.prob_loss,
            "var_95_pct": self.var_95_pct,
            "cvar_95_pct": self.cvar_95_pct,
            "best_ending": round(self.best_ending, 4),
            "worst_ending": round(self.worst_ending, 4),
            "ending_percentiles": {k: round(v, 4) for k, v in self.ending_percentiles.items()},
        }

    def summary(self) -> str:
        p = self.ending_percentiles
        return (
            f"{self.symbol or 'series'} — {self.method} MC, {self.n_paths} paths × "
            f"{self.horizon} bars from ${self.start_price:,.2f}\n"
            f"  expected return {self.expected_return_pct:+.2f}%  "
            f"(P[profit]={self.prob_profit:.0%}, P[loss]={self.prob_loss:.0%})\n"
            f"  ending price  p05 ${p.get(5, 0):,.2f} | p50 ${p.get(50, 0):,.2f} | "
            f"p95 ${p.get(95, 0):,.2f}\n"
            f"  95% VaR {self.var_95_pct:+.2f}%   95% CVaR {self.cvar_95_pct:+.2f}%   "
            f"range ${self.worst_ending:,.2f}–${self.best_ending:,.2f}"
        )


@dataclass(frozen=True)
class StressResult:
    scenario: str
    description: str
    start_price: float
    ending_price: float
    total_return_pct: float
    max_drawdown_pct: float
    horizon_days: int

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "description": self.description,
            "start_price": round(self.start_price, 4),
            "ending_price": round(self.ending_price, 4),
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "horizon_days": self.horizon_days,
        }


class MarketSimulator:
    """Fit a return process to history and project forward price paths."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    # --- parameter estimation ------------------------------------------------
    def estimate_params(
        self, bars: Sequence[Bar], *, halflife: int | None = None
    ) -> tuple[float, float]:
        """Estimate per-bar log-return drift ``mu`` and volatility ``sigma``.

        With ``halflife`` (in bars) the estimate is **recency-weighted**: each
        older return's weight decays by ½ every ``halflife`` bars, so the model
        tracks the live regime rather than averaging stale history. Without it,
        every bar is weighted equally. Returns ``(0.0, 0.0)`` on too few bars.
        """
        closes = [b.close for b in bars]
        rets = log_returns(closes)
        if len(rets) < 2:
            return 0.0, 0.0
        if halflife and halflife > 0:
            return self._ewma_params(rets, halflife)
        mu = sum(rets) / len(rets)
        var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
        return mu, var**0.5

    @staticmethod
    def _ewma_params(rets: Sequence[float], halflife: int) -> tuple[float, float]:
        """Recency-weighted drift/vol: weight ``decay**age`` with decay=½^(1/HL)."""
        decay = 0.5 ** (1.0 / halflife)
        n = len(rets)
        # Newest return (index n-1) gets weight 1; each older bar decays.
        weights = [decay ** (n - 1 - i) for i in range(n)]
        wsum = sum(weights)
        mu = sum(w * r for w, r in zip(weights, rets, strict=True)) / wsum
        var = sum(w * (r - mu) ** 2 for w, r in zip(weights, rets, strict=True)) / wsum
        return mu, var**0.5

    # --- engines -------------------------------------------------------------
    def gbm_paths(
        self,
        start_price: float,
        mu: float,
        sigma: float,
        horizon: int,
        n_paths: int,
    ) -> list[list[float]]:
        """Generate GBM price paths from per-bar log-return ``mu``/``sigma``."""
        # Drift correction so E[S_t] tracks exp(mu·t): the −σ²/2 Itô term.
        adj = mu - 0.5 * sigma * sigma
        paths: list[list[float]] = []
        for _ in range(n_paths):
            price = start_price
            path = [price]
            for _ in range(horizon):
                shock = self._rng.gauss(0.0, 1.0)
                price *= math.exp(adj + sigma * shock)
                path.append(price)
            paths.append(path)
        return paths

    def bootstrap_paths(
        self,
        start_price: float,
        historical_returns: Sequence[float],
        horizon: int,
        n_paths: int,
        block_size: int = 5,
    ) -> list[list[float]]:
        """Generate paths by resampling contiguous blocks of historical returns."""
        rets = list(historical_returns)
        if not rets:
            return [[start_price] * (horizon + 1) for _ in range(n_paths)]
        block = max(1, block_size)
        max_start = max(0, len(rets) - block)
        paths: list[list[float]] = []
        for _ in range(n_paths):
            sampled: list[float] = []
            while len(sampled) < horizon:
                begin = self._rng.randint(0, max_start)
                sampled.extend(rets[begin : begin + block])
            price = start_price
            path = [price]
            for r in sampled[:horizon]:
                price *= 1 + r
                path.append(price)
            paths.append(path)
        return paths

    def replay_scenario(self, start_price: float, scenario: Scenario) -> list[float]:
        """Deterministic price path from applying a scenario to ``start_price``."""
        return scenario.apply(start_price)

    # --- high-level entry points --------------------------------------------
    def simulate(
        self,
        bars: Sequence[Bar],
        config: SimulationConfig | None = None,
        *,
        symbol: str = "",
        spot_price: float | None = None,
    ) -> SimulationResult | None:
        """Fit to ``bars`` and run a Monte-Carlo projection per ``config``.

        ``spot_price`` overrides the starting price with a *live* value (e.g. the
        current quote mid) so projections are anchored to the market right now
        rather than the last completed bar's close. Returns ``None`` if the
        history is too short to start a path.
        """
        cfg = config or SimulationConfig()
        if cfg.seed is not None:
            self._rng.seed(cfg.seed)
        closes = [b.close for b in bars]
        if not closes:
            return None
        start_price = spot_price if spot_price and spot_price > 0 else closes[-1]

        if cfg.method == "bootstrap":
            from aoa.simulation.trends import simple_returns

            paths = self.bootstrap_paths(
                start_price, simple_returns(closes), cfg.horizon, cfg.n_paths, cfg.block_size
            )
        else:
            mu, sigma = self.estimate_params(bars, halflife=cfg.ewma_halflife)
            paths = self.gbm_paths(start_price, mu, sigma, cfg.horizon, cfg.n_paths)

        return self._summarize(symbol, cfg.method, start_price, cfg.horizon, paths)

    def stress_test(
        self, start_price: float, scenarios: Sequence[Scenario]
    ) -> list[StressResult]:
        """Replay each scenario from ``start_price`` and report the damage."""
        results: list[StressResult] = []
        for sc in scenarios:
            path = self.replay_scenario(start_price, sc)
            results.append(
                StressResult(
                    scenario=sc.name,
                    description=sc.description,
                    start_price=start_price,
                    ending_price=path[-1],
                    total_return_pct=sc.total_return_pct,
                    max_drawdown_pct=sc.max_drawdown_pct,
                    horizon_days=sc.horizon_days,
                )
            )
        return results

    # --- summary -------------------------------------------------------------
    def _summarize(
        self,
        symbol: str,
        method: str,
        start_price: float,
        horizon: int,
        paths: list[list[float]],
    ) -> SimulationResult:
        endings = sorted(p[-1] for p in paths)
        n = len(endings)
        mean_end = sum(endings) / n
        var_e = sum((e - mean_end) ** 2 for e in endings) / n if n else 0.0
        median_end = _percentile(endings, 50)

        wins = sum(1 for e in endings if e > start_price)
        pct = {p: _percentile(endings, p) for p in _PERCENTILES}

        # VaR / CVaR expressed as returns vs. the starting price.
        p5_price = pct[5]
        var_pct = (p5_price / start_price - 1) * 100 if start_price > 0 else 0.0
        tail_n = max(1, int(round(n * 0.05)))
        tail_mean = sum(endings[:tail_n]) / tail_n
        cvar_pct = (tail_mean / start_price - 1) * 100 if start_price > 0 else 0.0

        # Keep a representative spread of paths (best, worst, and evenly spaced).
        sample = self._sample_paths(paths)

        return SimulationResult(
            symbol=symbol.upper(),
            method=method,
            start_price=start_price,
            horizon=horizon,
            n_paths=n,
            mean_ending=mean_end,
            median_ending=median_end,
            std_ending=var_e**0.5,
            expected_return_pct=round((mean_end / start_price - 1) * 100, 2)
            if start_price > 0
            else 0.0,
            prob_profit=round(wins / n, 4) if n else 0.0,
            prob_loss=round((n - wins) / n, 4) if n else 0.0,
            var_95_pct=round(var_pct, 2),
            cvar_95_pct=round(cvar_pct, 2),
            best_ending=endings[-1],
            worst_ending=endings[0],
            ending_percentiles={k: round(v, 4) for k, v in pct.items()},
            sample_paths=sample,
        )

    @staticmethod
    def _sample_paths(paths: list[list[float]], k: int = 11) -> list[list[float]]:
        if len(paths) <= k:
            return [list(p) for p in paths]
        ordered = sorted(paths, key=lambda p: p[-1])
        idxs = sorted({int(round(i * (len(ordered) - 1) / (k - 1))) for i in range(k)})
        return [list(ordered[i]) for i in idxs]


def annualize_vol(per_bar_sigma: float, bars_per_year: int = TRADING_DAYS) -> float:
    """Convenience: scale a per-bar sigma to an annualized percentage."""
    return round(per_bar_sigma * (bars_per_year**0.5) * 100, 2)
