"""Tests for live, adaptive trend tracking and re-simulation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conftest import FakeBroker

from aoa.brokerage.base import BrokerError
from aoa.brokerage.models import Bar, Quote
from aoa.simulation.live import LiveMarketTracker
from aoa.simulation.simulator import MarketSimulator, SimulationConfig


def _bars(closes):
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            timestamp=base + timedelta(days=i),
            open=c,
            high=c * 1.01,
            low=c * 0.99,
            close=c,
            volume=1_000,
        )
        for i, c in enumerate(closes)
    ]


class ScriptedBroker(FakeBroker):
    """A fake broker whose quote/bars can be swapped between refreshes."""

    def __init__(self, bars, quote_mid):
        super().__init__()
        self._bars = bars
        self._quote_mid = quote_mid
        self.fail = False

    def set_market(self, bars, quote_mid):
        self._bars = bars
        self._quote_mid = quote_mid

    def get_quote(self, symbol: str) -> Quote:
        if self.fail:
            raise BrokerError("network down")
        half = 0.05
        return Quote(symbol=symbol, bid=self._quote_mid - half, ask=self._quote_mid + half)

    def get_bars(self, symbol, timeframe="1Day", limit=120):
        if self.fail:
            raise BrokerError("network down")
        return self._bars


def test_refresh_anchors_to_live_quote():
    closes = [100 * (1.002**i) for i in range(120)]
    broker = ScriptedBroker(_bars(closes), quote_mid=250.0)
    tracker = LiveMarketTracker(broker, sim_config=SimulationConfig(n_paths=100, seed=1))
    upd = tracker.refresh("AAPL")
    # Spot comes from the live quote mid, not the last bar close.
    assert upd.spot_price == 250.0
    assert upd.simulation is not None
    assert upd.simulation.start_price == 250.0
    assert upd.analysis is not None


def test_detects_regime_shift_between_refreshes():
    bull = _bars([100 * (1.01**i) for i in range(120)])
    bear = _bars([200 * (0.97**i) for i in range(120)])
    broker = ScriptedBroker(bull, quote_mid=bull[-1].close)
    tracker = LiveMarketTracker(broker, sim_config=SimulationConfig(n_paths=80, seed=1))

    first = tracker.refresh("AAPL")
    assert first.regime_changed is False  # no prior state
    assert "bull" in (first.regime or "")

    broker.set_market(bear, quote_mid=bear[-1].close)
    second = tracker.refresh("AAPL")
    assert second.regime_changed is True
    assert second.prev_regime == first.regime
    assert any("REGIME SHIFT" in n for n in second.notes)


def test_spot_change_and_move_alert():
    bars = _bars([100.0] * 120)
    broker = ScriptedBroker(bars, quote_mid=100.0)
    tracker = LiveMarketTracker(
        broker, sim_config=SimulationConfig(n_paths=50, seed=1), spot_move_alert_pct=2.0
    )
    tracker.refresh("X")
    broker.set_market(bars, quote_mid=105.0)  # +5%
    upd = tracker.refresh("X")
    assert upd.spot_change_pct == 5.0
    assert any("spot moved" in n for n in upd.notes)


def test_refresh_survives_broker_error():
    bars = _bars([100 * (1.001**i) for i in range(120)])
    broker = ScriptedBroker(bars, quote_mid=110.0)
    tracker = LiveMarketTracker(broker, sim_config=SimulationConfig(n_paths=50, seed=1))
    good = tracker.refresh("X")
    broker.fail = True
    bad = tracker.refresh("X")
    assert bad.error is not None
    # Holds the last known spot rather than crashing.
    assert bad.spot_price == good.spot_price
    assert bad.simulation is None


def test_stream_runs_fixed_iterations_with_injected_sleep():
    bars = _bars([100 * (1.001**i) for i in range(120)])
    broker = ScriptedBroker(bars, quote_mid=110.0)
    tracker = LiveMarketTracker(broker, sim_config=SimulationConfig(n_paths=40, seed=1))
    seen = []
    slept = []
    tracker.stream(
        ["AAPL", "MSFT"],
        interval=30.0,
        iterations=3,
        on_update=seen.append,
        sleep=slept.append,
    )
    assert len(seen) == 6  # 2 symbols × 3 iterations
    # Sleeps only *between* iterations, not after the last one.
    assert slept == [30.0, 30.0]


def test_stream_respects_market_gate():
    bars = _bars([100.0] * 120)
    broker = ScriptedBroker(bars, quote_mid=100.0)
    tracker = LiveMarketTracker(broker, sim_config=SimulationConfig(n_paths=20, seed=1))
    seen = []
    tracker.stream(
        ["X"],
        interval=1.0,
        iterations=2,
        on_update=seen.append,
        sleep=lambda _s: None,
        market_gate=lambda: False,  # market closed → no refreshes
    )
    assert seen == []


def test_ewma_params_track_recent_regime():
    sim = MarketSimulator(seed=1)
    # Calm for a long time, then a recent high-vol burst.
    calm = [100 * (1.0005**i) for i in range(200)]
    last = calm[-1]
    burst = []
    for i in range(20):
        last *= 1.05 if i % 2 == 0 else 0.95
        burst.append(last)
    bars = _bars(calm + burst)
    _, sigma_equal = sim.estimate_params(bars)
    _, sigma_ewma = sim.estimate_params(bars, halflife=10)
    # Recency weighting puts more weight on the volatile tail → higher sigma.
    assert sigma_ewma > sigma_equal
