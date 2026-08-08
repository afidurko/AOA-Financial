"""Walk-forward weight search for the research swarm.

Uses the lookahead-free backtest harness to score candidate ``swarm_weights``
configurations and optionally persist the winner for reproducibility.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from .backtest.engine import BacktestResult, backtest_universe
from .config import Config
from .databases.store import MarketStore


@dataclass
class TuneCandidate:
    weights: Dict[str, float]
    mean_excess: float
    mean_sharpe: float
    mean_hit_rate: float
    tickers_scored: int

    def to_dict(self) -> dict:
        return {
            "weights": dict(self.weights),
            "mean_excess": round(self.mean_excess, 6),
            "mean_sharpe": round(self.mean_sharpe, 4),
            "mean_hit_rate": round(self.mean_hit_rate, 4),
            "tickers_scored": self.tickers_scored,
        }


@dataclass
class TuneResult:
    metric: str
    best: TuneCandidate
    candidates: List[TuneCandidate] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "best": self.best.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
        }


def _score_results(results: Iterable[BacktestResult], metric: str) -> float:
    rows = list(results)
    if not rows:
        return float("-inf")
    if metric == "sharpe":
        return sum(r.sharpe for r in rows) / len(rows)
    if metric == "hit_rate":
        return sum(r.hit_rate for r in rows) / len(rows)
    return sum(r.excess_return for r in rows) / len(rows)


def _candidate_weight_sets(base: Dict[str, float]) -> List[Dict[str, float]]:
    """Small, auditable grid around the baseline weights."""
    candidates = [dict(base)]
    for agent in base:
        boosted = dict(base)
        boosted[agent] = round(base[agent] * 1.25, 4)
        candidates.append(boosted)
        trimmed = dict(base)
        trimmed[agent] = round(base[agent] * 0.75, 4)
        candidates.append(trimmed)
    # De-duplicate while preserving order.
    seen: set[tuple[tuple[str, float], ...]] = set()
    unique: List[Dict[str, float]] = []
    for weights in candidates:
        key = tuple(sorted(weights.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(weights)
    return unique


def tune_swarm_weights(
    store: MarketStore,
    tickers: Sequence[str],
    *,
    horizon: int = 21,
    step: int | None = None,
    config: Config | None = None,
    metric: str = "excess_return",
    limit_candidates: int | None = None,
) -> TuneResult:
    """Score weight variants via walk-forward backtest; return the best set."""
    config = config or Config()
    metric = metric if metric in {"excess_return", "sharpe", "hit_rate"} else "excess_return"
    base = dict(config.swarm_weights)
    scored: List[TuneCandidate] = []
    weight_sets = _candidate_weight_sets(base)
    if limit_candidates is not None:
        weight_sets = weight_sets[: max(1, limit_candidates)]

    for weights in weight_sets:
        trial = copy.copy(config)
        trial.swarm_weights = weights
        results = backtest_universe(
            store,
            tickers,
            horizon=horizon,
            step=step,
            config=trial,
        )
        rows = list(results.values())
        scored.append(
            TuneCandidate(
                weights=weights,
                mean_excess=_score_results(rows, "excess_return"),
                mean_sharpe=_score_results(rows, "sharpe"),
                mean_hit_rate=_score_results(rows, "hit_rate"),
                tickers_scored=len(rows),
            )
        )

    scored.sort(key=lambda c: _candidate_score(c, metric), reverse=True)
    return TuneResult(metric=metric, best=scored[0], candidates=scored)


def _candidate_score(candidate: TuneCandidate, metric: str) -> float:
    if metric == "sharpe":
        return candidate.mean_sharpe
    if metric == "hit_rate":
        return candidate.mean_hit_rate
    return candidate.mean_excess


def save_tuned_weights(path: Path, result: TuneResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
