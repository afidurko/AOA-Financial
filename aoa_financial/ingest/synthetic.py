"""Deterministic synthetic market-history generator.

Produces realistic-looking daily OHLCV history for *any* ticker back to June
1960, with no network required. The series is built from a regime-switching
geometric Brownian motion overlaid with long macro cycles, so the downstream
regime / factor / forecast models have genuine structure to discover.

Determinism: identical ``(ticker, end_date)`` inputs always yield identical
history (the RNG is seeded from a hash of the ticker), which makes runs
reproducible and tests stable.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Tuple

from ..config import EPOCH_START, TRADING_DAYS_PER_YEAR
from ..databases.store import Bar

# Sector archetypes: (annual drift, annual vol, dividend bias). These shape the
# personality of a generated security so a utility behaves unlike a tech name.
_SECTORS: Dict[str, Tuple[float, float, float]] = {
    "Technology":        (0.135, 0.34, 0.005),
    "Financials":        (0.090, 0.28, 0.025),
    "Energy":            (0.075, 0.32, 0.040),
    "Healthcare":        (0.110, 0.22, 0.015),
    "Consumer Staples":  (0.080, 0.16, 0.028),
    "Consumer Disc.":    (0.105, 0.27, 0.012),
    "Industrials":       (0.085, 0.24, 0.020),
    "Communications":    (0.070, 0.26, 0.030),
}

# Latent regimes the price process switches between. Each: (daily drift mult,
# daily vol mult, mean dwell time in days). Drift/vol are multipliers on the
# security's baseline so a "crash" regime is sharp and short, a "bull" long.
_REGIMES = {
    "bull":       (1.6, 0.9, 320),
    "sideways":   (0.1, 1.0, 180),
    "correction": (-1.4, 1.7, 45),
    "crash":      (-3.2, 2.6, 20),
    "recovery":   (2.2, 1.4, 90),
}
_REGIME_NAMES = list(_REGIMES)


@dataclass
class SyntheticSeries:
    ticker: str
    sector: str
    bars: List[Bar]
    fundamentals: Dict[str, float]
    sentiment: float


class SyntheticGenerator:
    def __init__(self, epoch_start: date = EPOCH_START):
        self.epoch_start = epoch_start

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _seed(ticker: str) -> int:
        h = hashlib.sha256(ticker.upper().encode()).hexdigest()
        return int(h[:16], 16)

    def _sector_for(self, ticker: str, rng: random.Random) -> str:
        names = list(_SECTORS)
        return names[self._seed(ticker) % len(names)]

    @staticmethod
    def _trading_days(start: date, end: date) -> List[date]:
        days, d = [], start
        one = timedelta(days=1)
        while d <= end:
            if d.weekday() < 5:  # Mon-Fri
                days.append(d)
            d += one
        return days

    # -- core generation --------------------------------------------------
    def generate(self, ticker: str, end: date | None = None,
                 start_price: float | None = None) -> SyntheticSeries:
        end = end or date.today()
        rng = random.Random(self._seed(ticker))
        sector = self._sector_for(ticker, rng)
        base_drift, base_vol, div_bias = _SECTORS[sector]

        days = self._trading_days(self.epoch_start, end)
        if not days:
            raise ValueError("empty date range")

        # Per-day baseline parameters.
        mu = base_drift / TRADING_DAYS_PER_YEAR
        sigma = base_vol / math.sqrt(TRADING_DAYS_PER_YEAR)

        price = start_price or rng.uniform(2.0, 25.0)
        regime = "sideways"
        dwell = _REGIMES[regime][2]

        # A slow secular macro cycle (~ every 11 years) modulating drift, so the
        # whole market breathes and regimes inherited by every ticker correlate
        # loosely with calendar time.
        macro_period = TRADING_DAYS_PER_YEAR * 11

        bars: List[Bar] = []
        for i, d in enumerate(days):
            # Regime transition (Markov-ish via dwell countdown).
            dwell -= 1
            if dwell <= 0:
                regime = self._next_regime(regime, rng)
                dwell = max(5, int(rng.expovariate(1.0 / _REGIMES[regime][2])))
            dmult, vmult, _ = _REGIMES[regime]

            macro = 0.6 * math.sin(2 * math.pi * i / macro_period)
            day_mu = mu * (1.0 + macro) + (mu * (dmult - 1.0))
            day_sigma = sigma * vmult

            shock = rng.gauss(0.0, 1.0)
            ret = day_mu + day_sigma * shock
            ret = max(-0.45, min(0.45, ret))  # clamp pathological tails

            open_p = price
            close_p = max(0.01, open_p * math.exp(ret))
            # Intraday range proportional to realised vol.
            spread = abs(rng.gauss(0.0, day_sigma)) * open_p
            high_p = max(open_p, close_p) + spread
            low_p = max(0.01, min(open_p, close_p) - spread)
            volume = int(max(1_000, rng.lognormvariate(13.5, 0.6)))

            bars.append(Bar(d.isoformat(), round(open_p, 4), round(high_p, 4),
                            round(low_p, 4), round(close_p, 4), volume))
            price = close_p

        fundamentals = self._fundamentals(rng, sector, div_bias, bars)
        sentiment = self._sentiment(bars)
        return SyntheticSeries(ticker.upper(), sector, bars, fundamentals, sentiment)

    @staticmethod
    def _next_regime(current: str, rng: random.Random) -> str:
        # Transition matrix encoding plausible regime flow (e.g. crash tends to
        # be followed by recovery, not another bull).
        transitions = {
            "bull":       [("bull", .55), ("sideways", .25), ("correction", .15), ("crash", .05)],
            "sideways":   [("bull", .35), ("sideways", .35), ("correction", .20), ("recovery", .10)],
            "correction": [("recovery", .40), ("sideways", .30), ("crash", .20), ("bull", .10)],
            "crash":      [("recovery", .65), ("correction", .25), ("sideways", .10)],
            "recovery":   [("bull", .50), ("sideways", .30), ("correction", .20)],
        }
        r = rng.random()
        acc = 0.0
        for name, p in transitions[current]:
            acc += p
            if r <= acc:
                return name
        return "sideways"

    @staticmethod
    def _fundamentals(rng: random.Random, sector: str, div_bias: float,
                      bars: List[Bar]) -> Dict[str, float]:
        # Derive coarse fundamentals consistent with the realised trend.
        recent = bars[-min(len(bars), TRADING_DAYS_PER_YEAR):]
        trend = (recent[-1].close / recent[0].close) - 1.0 if recent else 0.0
        growth = max(-0.3, min(0.6, 0.05 + 0.5 * trend + rng.gauss(0, 0.04)))
        return {
            "pe_ratio": round(max(4.0, rng.gauss(20, 8) + 30 * max(0, trend)), 2),
            "pb_ratio": round(max(0.3, rng.gauss(3.0, 1.5)), 2),
            "dividend_yield": round(max(0.0, rng.gauss(div_bias, 0.01)), 4),
            "revenue_growth": round(growth, 4),
            "profit_margin": round(max(-0.2, rng.gauss(0.12, 0.07)), 4),
            "debt_to_equity": round(max(0.0, rng.gauss(0.9, 0.5)), 3),
            "roe": round(rng.gauss(0.14, 0.08), 4),
            "free_cash_flow": round(rng.gauss(1.0, 0.8), 3),
        }

    @staticmethod
    def _sentiment(bars: List[Bar]) -> float:
        # Sentiment loosely tracks recent momentum, with noise.
        window = bars[-21:]
        if len(window) < 2:
            return 0.0
        mom = (window[-1].close / window[0].close) - 1.0
        return max(-1.0, min(1.0, math.tanh(8 * mom)))
