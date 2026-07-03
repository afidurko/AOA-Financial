"""Live, adaptive trend tracking and re-simulation.

The analysis and simulator modules are stateless: hand them a bar history and
they describe it. This module makes them **dynamic** — it polls the broker for
fresh quotes and bars, recomputes the trend, re-fits the (recency-weighted)
simulation to the *current* regime, anchors projections to the **live quote**,
and reports what changed since the last refresh: regime flips, notable spot
moves, and drawdown transitions.

It depends only on the abstract :class:`~aoa.brokerage.base.Broker`, so it works
identically against Alpaca live, the paper sandbox, or the in-memory fake broker
used in tests. Each refresh is optionally written to the JSONL journal, giving
the same audit trail the trading swarm produces.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aoa.brokerage.base import Broker, BrokerError
from aoa.brokerage.models import Quote
from aoa.journal.store import Journal
from aoa.simulation.simulator import MarketSimulator, SimulationConfig, SimulationResult
from aoa.simulation.trends import TrendAnalysis, analyze_trends


@dataclass(frozen=True)
class LiveUpdate:
    """A single point-in-time snapshot of a symbol's live state + projection."""

    symbol: str
    timestamp: datetime
    spot_price: float  # live quote mid (falls back to last bar close)
    quote: Quote | None
    analysis: TrendAnalysis | None
    simulation: SimulationResult | None
    regime: str | None
    prev_regime: str | None
    regime_changed: bool
    spot_change_pct: float | None  # vs. the previous update's spot
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "spot_price": round(self.spot_price, 4),
            "regime": self.regime,
            "prev_regime": self.prev_regime,
            "regime_changed": self.regime_changed,
            "spot_change_pct": self.spot_change_pct,
            "trend": self.analysis.trend if self.analysis else None,
            "expected_return_pct": (
                self.simulation.expected_return_pct if self.simulation else None
            ),
            "var_95_pct": self.simulation.var_95_pct if self.simulation else None,
            "notes": self.notes,
            "error": self.error,
        }

    def summary(self) -> str:
        if self.error:
            return f"{self.symbol}: ERROR — {self.error}"
        a, s = self.analysis, self.simulation
        chg = f"{self.spot_change_pct:+.2f}%" if self.spot_change_pct is not None else "—"
        line = (
            f"{self.symbol} ${self.spot_price:,.2f} ({chg})  "
            f"trend={a.trend if a else '?'} regime={self.regime or '?'}"
        )
        if s:
            line += (
                f"  | {s.horizon}-bar E[r]={s.expected_return_pct:+.2f}% "
                f"P(profit)={s.prob_profit:.0%} VaR95={s.var_95_pct:+.2f}%"
            )
        if self.notes:
            line += "\n    " + "; ".join(self.notes)
        return line


class LiveMarketTracker:
    """Polls the broker and re-runs analysis + simulation as the market moves."""

    def __init__(
        self,
        broker: Broker,
        *,
        timeframe: str = "1Day",
        bar_limit: int = 252,
        sim_config: SimulationConfig | None = None,
        simulator: MarketSimulator | None = None,
        # Adapt to the live regime by default: half-weight returns older than
        # ~one trading quarter.
        ewma_halflife: int | None = 63,
        spot_move_alert_pct: float = 2.0,
        journal: Journal | None = None,
    ):
        self.broker = broker
        self.timeframe = timeframe
        self.bar_limit = bar_limit
        base = sim_config or SimulationConfig()
        # Fold the adaptive half-life into the config unless the caller set one.
        self.sim_config = (
            base
            if base.ewma_halflife is not None
            else SimulationConfig(
                method=base.method,
                horizon=base.horizon,
                n_paths=base.n_paths,
                block_size=base.block_size,
                seed=base.seed,
                ewma_halflife=ewma_halflife,
            )
        )
        self.simulator = simulator or MarketSimulator(seed=self.sim_config.seed)
        self.spot_move_alert_pct = spot_move_alert_pct
        self.journal = journal
        self._last: dict[str, LiveUpdate] = {}

    def last_update(self, symbol: str) -> LiveUpdate | None:
        return self._last.get(symbol.upper())

    def refresh(self, symbol: str) -> LiveUpdate:
        """Pull fresh live data for ``symbol`` and recompute everything."""
        symbol = symbol.upper()
        prev = self._last.get(symbol)
        now = datetime.now(timezone.utc)
        try:
            quote = self.broker.get_quote(symbol)
            bars = self.broker.get_bars(symbol, self.timeframe, self.bar_limit)
        except BrokerError as exc:
            update = LiveUpdate(
                symbol=symbol,
                timestamp=now,
                spot_price=prev.spot_price if prev else 0.0,
                quote=None,
                analysis=prev.analysis if prev else None,
                simulation=None,
                regime=prev.regime if prev else None,
                prev_regime=prev.regime if prev else None,
                regime_changed=False,
                spot_change_pct=None,
                notes=["data fetch failed — holding last known state"],
                error=str(exc),
            )
            self._last[symbol] = update
            return update

        spot = quote.mid if quote and quote.mid > 0 else (bars[-1].close if bars else 0.0)
        analysis = analyze_trends(bars, symbol)
        simulation = self.simulator.simulate(
            bars, self.sim_config, symbol=symbol, spot_price=spot
        )

        regime = analysis.regime if analysis else None
        prev_regime = prev.regime if prev else None
        regime_changed = bool(prev_regime and regime and regime != prev_regime)
        spot_change = (
            round((spot / prev.spot_price - 1) * 100, 2)
            if prev and prev.spot_price > 0
            else None
        )

        notes = self._build_notes(
            analysis, regime_changed, prev_regime, regime, spot_change
        )
        update = LiveUpdate(
            symbol=symbol,
            timestamp=now,
            spot_price=spot,
            quote=quote,
            analysis=analysis,
            simulation=simulation,
            regime=regime,
            prev_regime=prev_regime,
            regime_changed=regime_changed,
            spot_change_pct=spot_change,
            notes=notes,
        )
        self._last[symbol] = update
        if self.journal is not None:
            self.journal.record("live_update", update.to_dict())
        return update

    def refresh_all(self, symbols: Sequence[str]) -> list[LiveUpdate]:
        return [self.refresh(s) for s in symbols]

    def stream(
        self,
        symbols: Sequence[str],
        *,
        interval: float = 60.0,
        iterations: int | None = None,
        on_update: Callable[[LiveUpdate], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        market_gate: Callable[[], bool] | None = None,
    ) -> None:
        """Continuously refresh ``symbols`` every ``interval`` seconds.

        Runs forever unless ``iterations`` is given. ``on_update`` is invoked for
        each :class:`LiveUpdate`. ``market_gate`` (e.g. ``broker.is_market_open``)
        can skip refreshes while the market is closed. ``sleep`` is injectable so
        tests can drive the loop without real time.
        """
        count = 0
        while iterations is None or count < iterations:
            if market_gate is None or market_gate():
                for sym in symbols:
                    update = self.refresh(sym)
                    if on_update is not None:
                        on_update(update)
            count += 1
            if iterations is not None and count >= iterations:
                break
            sleep(interval)

    # --- helpers -------------------------------------------------------------
    def _build_notes(
        self,
        analysis: TrendAnalysis | None,
        regime_changed: bool,
        prev_regime: str | None,
        regime: str | None,
        spot_change: float | None,
    ) -> list[str]:
        notes: list[str] = []
        if regime_changed:
            notes.append(f"REGIME SHIFT: {prev_regime} → {regime}")
        if spot_change is not None and abs(spot_change) >= self.spot_move_alert_pct:
            notes.append(f"spot moved {spot_change:+.2f}% since last refresh")
        if analysis is not None:
            if analysis.current_drawdown_pct <= -10.0:
                notes.append(
                    f"in drawdown {analysis.current_drawdown_pct:.1f}% from peak"
                )
            if analysis.returns.annualized_vol_pct >= 40.0:
                notes.append(
                    f"elevated volatility (ann. {analysis.returns.annualized_vol_pct:.0f}%)"
                )
        return notes
