"""Incremental indicator kernels and strategy-family signal rules.

Every kernel is *streaming*: it consumes one value per bar and returns the
indicator value for that bar (or ``None`` during warm-up). The semantics follow
Pine Script's ``ta.*`` built-ins so the Python emulator and the generated Pine
strategy agree bar-for-bar:

* ``Ema``        — ``ta.ema``: alpha = 2/(len+1), seeded with the first value.
* ``Rma``        — ``ta.rma`` (Wilder): alpha = 1/len, seeded with SMA(len).
* ``Rsi``        — ``ta.rsi`` on RMA of gains / losses.
* ``Atr``        — ``ta.atr``: RMA of true range.
* ``Stdev``      — ``ta.stdev`` (population / biased, Pine's default).
* ``Supertrend`` — ``ta.supertrend(factor, atrPeriod)``; direction ``-1`` = up.
* ``SessionVwap``— ``ta.vwap`` anchored to the session (calendar day).

Strategies return a :class:`Signal` for each bar *at the bar close*. Fills and
stops belong to the emulator (:mod:`aoa.tradingview.backtest`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from aoa.brokerage.models import Bar
from aoa.tradingview.presets import Preset

_NY = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------- #
# Kernels
# --------------------------------------------------------------------------- #


class Sma:
    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self._win: deque[float] = deque(maxlen=self.length)
        self._sum = 0.0
        self.value: float | None = None

    def update(self, x: float) -> float | None:
        if len(self._win) == self.length:
            self._sum -= self._win[0]
        self._win.append(x)
        self._sum += x
        if len(self._win) < self.length:
            self.value = None
        else:
            self.value = self._sum / self.length
        return self.value


class Ema:
    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self.alpha = 2.0 / (self.length + 1.0)
        self.value: float | None = None
        self._n = 0

    def update(self, x: float) -> float | None:
        self._n += 1
        if self.value is None:
            self.value = x
        else:
            self.value = self.alpha * x + (1.0 - self.alpha) * self.value
        # Pine's ta.ema is defined from bar 1; we mark the first ``length`` bars as
        # warm-up so downstream crossovers do not fire on seed noise.
        return self.value if self._n >= self.length else None

    @property
    def raw(self) -> float | None:
        return self.value


class Rma:
    """Wilder moving average (Pine ``ta.rma``), SMA-seeded."""

    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self.value: float | None = None
        self._seed: list[float] = []

    def update(self, x: float) -> float | None:
        if self.value is None:
            self._seed.append(x)
            if len(self._seed) < self.length:
                return None
            self.value = sum(self._seed) / self.length
            return self.value
        self.value = (self.value * (self.length - 1) + x) / self.length
        return self.value


class Rsi:
    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self._up = Rma(self.length)
        self._down = Rma(self.length)
        self._prev: float | None = None
        self.value: float | None = None

    def update(self, x: float) -> float | None:
        if self._prev is None:
            self._prev = x
            return None
        delta = x - self._prev
        self._prev = x
        up = self._up.update(max(delta, 0.0))
        down = self._down.update(max(-delta, 0.0))
        if up is None or down is None:
            self.value = None
        elif down == 0:
            self.value = 100.0
        elif up == 0:
            self.value = 0.0
        else:
            self.value = 100.0 - 100.0 / (1.0 + up / down)
        return self.value


class Atr:
    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self._rma = Rma(self.length)
        self._prev_close: float | None = None
        self.value: float | None = None

    def update(self, bar: Bar) -> float | None:
        if self._prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - self._prev_close),
                abs(bar.low - self._prev_close),
            )
        self._prev_close = bar.close
        self.value = self._rma.update(tr)
        return self.value


class Stdev:
    """Population standard deviation over a rolling window (Pine default)."""

    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self._win: deque[float] = deque(maxlen=self.length)
        self._sum = 0.0
        self._sumsq = 0.0
        self.value: float | None = None
        self.mean: float | None = None

    def update(self, x: float) -> float | None:
        if len(self._win) == self.length:
            old = self._win[0]
            self._sum -= old
            self._sumsq -= old * old
        self._win.append(x)
        self._sum += x
        self._sumsq += x * x
        if len(self._win) < self.length:
            self.value = None
            self.mean = None
            return None
        n = self.length
        mean = self._sum / n
        var = max(self._sumsq / n - mean * mean, 0.0)
        self.mean = mean
        self.value = var**0.5
        return self.value


class Highest:
    """Rolling maximum of the *previous* ``length`` values (``ta.highest(x, len)[1]``)."""

    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self._win: deque[float] = deque(maxlen=self.length)

    def prior(self) -> float | None:
        if len(self._win) < self.length:
            return None
        return max(self._win)

    def push(self, x: float) -> None:
        self._win.append(x)


class Lowest:
    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self._win: deque[float] = deque(maxlen=self.length)

    def prior(self) -> float | None:
        if len(self._win) < self.length:
            return None
        return min(self._win)

    def push(self, x: float) -> None:
        self._win.append(x)


class Macd:
    def __init__(self, fast: int, slow: int, signal: int) -> None:
        self._fast = Ema(fast)
        self._slow = Ema(slow)
        self._signal = Ema(signal)
        self.macd: float | None = None
        self.signal: float | None = None
        self.hist: float | None = None

    def update(self, x: float) -> float | None:
        f = self._fast.update(x)
        s = self._slow.update(x)
        if f is None or s is None:
            self.macd = self.signal = self.hist = None
            return None
        self.macd = f - s
        sig = self._signal.update(self.macd)
        if sig is None:
            self.signal = self.hist = None
            return None
        self.signal = sig
        self.hist = self.macd - sig
        return self.hist


class Supertrend:
    """Pine ``ta.supertrend``. ``direction`` is -1 in an uptrend, +1 in a downtrend."""

    def __init__(self, factor: float, atr_length: int) -> None:
        self.factor = float(factor)
        self._atr = Atr(atr_length)
        self._prev_upper: float | None = None
        self._prev_lower: float | None = None
        self._prev_close: float | None = None
        self.direction: int | None = None
        self.value: float | None = None

    def update(self, bar: Bar) -> int | None:
        atr = self._atr.update(bar)
        if atr is None:
            self._prev_close = bar.close
            return None
        hl2 = (bar.high + bar.low) / 2.0
        upper = hl2 + self.factor * atr
        lower = hl2 - self.factor * atr
        pc = self._prev_close if self._prev_close is not None else bar.close
        if self._prev_lower is not None and not (lower > self._prev_lower or pc < self._prev_lower):
            lower = self._prev_lower
        if self._prev_upper is not None and not (upper < self._prev_upper or pc > self._prev_upper):
            upper = self._prev_upper
        if self.direction is None:
            direction = 1
        elif self.value == self._prev_upper:
            direction = -1 if bar.close > upper else 1
        else:
            direction = 1 if bar.close < lower else -1
        self.direction = direction
        self.value = lower if direction == -1 else upper
        self._prev_upper = upper
        self._prev_lower = lower
        self._prev_close = bar.close
        return self.direction


class SessionVwap:
    """Volume-weighted average price anchored to the session day."""

    def __init__(self, market: str) -> None:
        self.market = market
        self._day: Any = None
        self._pv = 0.0
        self._v = 0.0
        self.value: float | None = None

    def _session_key(self, ts: datetime) -> Any:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if self.market == "equity":
            return ts.astimezone(_NY).date()
        return ts.astimezone(timezone.utc).date()

    def update(self, bar: Bar) -> float | None:
        key = self._session_key(bar.timestamp)
        if key != self._day:
            self._day = key
            self._pv = 0.0
            self._v = 0.0
        typical = (bar.high + bar.low + bar.close) / 3.0
        self._pv += typical * bar.volume
        self._v += bar.volume
        self.value = self._pv / self._v if self._v > 0 else typical
        return self.value


class RollingSum:
    def __init__(self, length: int) -> None:
        self.length = max(1, int(length))
        self._win: deque[float] = deque(maxlen=self.length)
        self._sum = 0.0
        self.value: float | None = None

    def update(self, x: float) -> float | None:
        if len(self._win) == self.length:
            self._sum -= self._win[0]
        self._win.append(x)
        self._sum += x
        self.value = self._sum if len(self._win) == self.length else None
        return self.value


def crossover(prev_a: float | None, a: float | None, prev_b: float | None, b: float | None) -> bool:
    if None in (prev_a, a, prev_b, b):
        return False
    return prev_a <= prev_b and a > b  # type: ignore[operator]


def crossunder(prev_a: float | None, a: float | None, prev_b: float | None, b: float | None) -> bool:
    if None in (prev_a, a, prev_b, b):
        return False
    return prev_a >= prev_b and a < b  # type: ignore[operator]


def in_session(ts: datetime, session: str | None, market: str) -> bool:
    """Pine-style ``HHMM-HHMM`` session filter (exchange-local for equities)."""
    if not session:
        return True
    start, end = session.split("-")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    local = ts.astimezone(_NY) if market == "equity" else ts.astimezone(timezone.utc)
    hhmm = local.hour * 100 + local.minute
    return int(start) <= hhmm < int(end)


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #


@dataclass
class Signal:
    long_entry: bool = False
    short_entry: bool = False
    exit_long: bool = False
    exit_short: bool = False
    atr: float | None = None
    ready: bool = False
    features: dict[str, float] = field(default_factory=dict)

    def any(self) -> bool:
        return self.long_entry or self.short_entry or self.exit_long or self.exit_short


class Strategy(Protocol):
    preset: Preset
    warmup: int

    def on_bar(self, bar: Bar) -> Signal: ...


class _Base:
    def __init__(self, preset: Preset) -> None:
        self.preset = preset
        self.params = preset.params
        self.allow_short = preset.allow_short
        self._atr = Atr(int(self.params.get("atr_len", 14)))
        self.warmup = 0

    def _finish(self, sig: Signal, atr: float | None) -> Signal:
        sig.atr = atr
        if not self.allow_short:
            sig.short_entry = False
            sig.exit_short = False
        return sig


class MomentumScalper(_Base):
    def __init__(self, preset: Preset) -> None:
        super().__init__(preset)
        p = self.params
        self.fast = Ema(int(p["ema_fast"]))
        self.slow = Ema(int(p["ema_slow"]))
        self.rsi = Rsi(int(p["rsi_len"]))
        self.vol = Sma(int(p.get("vol_len", 20)))
        self.vwap = SessionVwap(preset.market) if p.get("use_vwap", True) else None
        self.rsi_floor = float(p.get("rsi_floor", 52.0))
        self.rsi_ceiling = float(p.get("rsi_ceiling", 85.0))
        self.vol_mult = float(p.get("vol_mult", 1.0))
        self._pf: float | None = None
        self._ps: float | None = None
        self._pr: float | None = None
        self.warmup = max(int(p["ema_slow"]), int(p["rsi_len"]) + 1, int(p.get("vol_len", 20))) + 1

    def on_bar(self, bar: Bar) -> Signal:
        f = self.fast.update(bar.close)
        s = self.slow.update(bar.close)
        r = self.rsi.update(bar.close)
        v = self.vol.update(bar.volume)
        vw = self.vwap.update(bar) if self.vwap else None
        atr = self._atr.update(bar)
        sig = Signal()
        if None not in (f, s, r, v, atr):
            sig.ready = True
            vol_ok = bar.volume >= self.vol_mult * v if v and v > 0 else True  # type: ignore[operator]
            above_vwap = vw is None or bar.close > vw
            below_vwap = vw is None or bar.close < vw
            cross_up = crossover(self._pf, f, self._ps, s)
            cross_dn = crossunder(self._pf, f, self._ps, s)
            rsi_up = crossover(self._pr, r, self.rsi_floor, self.rsi_floor)
            rsi_dn = crossunder(self._pr, r, 100.0 - self.rsi_floor, 100.0 - self.rsi_floor)
            trend_up = f > s  # type: ignore[operator]
            long_trigger = cross_up or (trend_up and rsi_up)
            short_trigger = cross_dn or ((not trend_up) and rsi_dn)
            sig.long_entry = bool(
                long_trigger and self.rsi_floor < r < self.rsi_ceiling and above_vwap and vol_ok  # type: ignore[operator]
            )
            sig.short_entry = bool(
                short_trigger
                and (100.0 - self.rsi_ceiling) < r < (100.0 - self.rsi_floor)  # type: ignore[operator]
                and below_vwap
                and vol_ok
            )
            sig.exit_long = cross_dn
            sig.exit_short = cross_up
            sig.features = {"ema_fast": f, "ema_slow": s, "rsi": r}  # type: ignore[dict-item]
        self._pf, self._ps, self._pr = f, s, r
        return self._finish(sig, atr)


class MeanReversionBands(_Base):
    def __init__(self, preset: Preset) -> None:
        super().__init__(preset)
        p = self.params
        self.basis = Sma(int(p["bb_len"]))
        self.sd = Stdev(int(p["bb_len"]))
        self.mult = float(p["bb_mult"])
        self.rsi = Rsi(int(p["rsi_len"]))
        self.rsi_low = float(p.get("rsi_low", 30.0))
        self.rsi_high = float(p.get("rsi_high", 70.0))
        self._pc: float | None = None
        self._pb: float | None = None
        self.warmup = max(int(p["bb_len"]), int(p["rsi_len"]) + 1) + 1

    def on_bar(self, bar: Bar) -> Signal:
        b = self.basis.update(bar.close)
        sd = self.sd.update(bar.close)
        r = self.rsi.update(bar.close)
        atr = self._atr.update(bar)
        sig = Signal()
        if None not in (b, sd, r, atr):
            sig.ready = True
            upper = b + self.mult * sd  # type: ignore[operator]
            lower = b - self.mult * sd  # type: ignore[operator]
            sig.long_entry = bar.close < lower and r < self.rsi_low  # type: ignore[operator]
            sig.short_entry = bar.close > upper and r > self.rsi_high  # type: ignore[operator]
            sig.exit_long = crossover(self._pc, bar.close, self._pb, b)
            sig.exit_short = crossunder(self._pc, bar.close, self._pb, b)
            sig.features = {"basis": b, "upper": upper, "lower": lower, "rsi": r}  # type: ignore[dict-item]
        self._pc, self._pb = bar.close, b
        return self._finish(sig, atr)


class BreakoutDonchian(_Base):
    def __init__(self, preset: Preset) -> None:
        super().__init__(preset)
        p = self.params
        self.hi = Highest(int(p["channel_len"]))
        self.lo = Lowest(int(p["channel_len"]))
        self.exit_lo = Lowest(int(p.get("exit_channel_len", p["channel_len"] // 2 or 1)))
        self.exit_hi = Highest(int(p.get("exit_channel_len", p["channel_len"] // 2 or 1)))
        self.vol = Sma(int(p.get("vol_len", 20)))
        self.vol_mult = float(p.get("vol_mult", 1.0))
        self.warmup = max(int(p["channel_len"]), int(p.get("vol_len", 20))) + 2

    def on_bar(self, bar: Bar) -> Signal:
        upper = self.hi.prior()
        lower = self.lo.prior()
        exit_lower = self.exit_lo.prior()
        exit_upper = self.exit_hi.prior()
        v = self.vol.update(bar.volume)
        atr = self._atr.update(bar)
        sig = Signal()
        if None not in (upper, lower, exit_lower, exit_upper, v, atr):
            sig.ready = True
            vol_ok = bar.volume >= self.vol_mult * v if v and v > 0 else True  # type: ignore[operator]
            sig.long_entry = bar.close > upper and vol_ok  # type: ignore[operator]
            sig.short_entry = bar.close < lower and vol_ok  # type: ignore[operator]
            sig.exit_long = bar.close < exit_lower  # type: ignore[operator]
            sig.exit_short = bar.close > exit_upper  # type: ignore[operator]
            sig.features = {"upper": upper, "lower": lower}  # type: ignore[dict-item]
        self.hi.push(bar.high)
        self.lo.push(bar.low)
        self.exit_lo.push(bar.low)
        self.exit_hi.push(bar.high)
        return self._finish(sig, atr)


class TrendSupertrendMacd(_Base):
    def __init__(self, preset: Preset) -> None:
        super().__init__(preset)
        p = self.params
        self.st = Supertrend(float(p["st_mult"]), int(p["st_len"]))
        self.macd = Macd(int(p["macd_fast"]), int(p["macd_slow"]), int(p["macd_signal"]))
        self._pd: int | None = None
        self.warmup = int(p["macd_slow"]) + int(p["macd_signal"]) + int(p["st_len"]) + 1

    def on_bar(self, bar: Bar) -> Signal:
        d = self.st.update(bar)
        hist = self.macd.update(bar.close)
        atr = self._atr.update(bar)
        sig = Signal()
        if d is not None and hist is not None and atr is not None:
            sig.ready = True
            flipped_up = self._pd == 1 and d == -1
            flipped_dn = self._pd == -1 and d == 1
            sig.long_entry = d == -1 and hist > 0 and (flipped_up or self._pd is None)
            sig.short_entry = d == 1 and hist < 0 and (flipped_dn or self._pd is None)
            sig.exit_long = flipped_dn
            sig.exit_short = flipped_up
            sig.features = {"direction": float(d), "macd_hist": hist, "supertrend": float(self.st.value or 0.0)}
        self._pd = d
        return self._finish(sig, atr)


class OrderflowImbalance(_Base):
    """Bar-level order-flow proxy: close-location-value × volume, z-scored."""

    def __init__(self, preset: Preset) -> None:
        super().__init__(preset)
        p = self.params
        n = int(p["delta_len"])
        self.cum = RollingSum(n)
        self.z = Stdev(max(3 * n, 10))
        self.z_entry = float(p["z_entry"])
        self.z_exit = float(p.get("z_exit", 0.0))
        self.vwap = SessionVwap(preset.market) if p.get("use_vwap", True) else None
        self.vol = Sma(int(p.get("vol_len", 20)))
        self.vol_mult = float(p.get("vol_mult", 1.0))
        self.warmup = max(3 * n, 10) + n + 1

    def on_bar(self, bar: Bar) -> Signal:
        rng = bar.high - bar.low
        clv = (2.0 * (bar.close - bar.low) / rng - 1.0) if rng > 0 else 0.0
        delta = clv * bar.volume
        cum = self.cum.update(delta)
        vw = self.vwap.update(bar) if self.vwap else None
        v = self.vol.update(bar.volume)
        atr = self._atr.update(bar)
        sig = Signal()
        if cum is not None:
            sd = self.z.update(cum)
            if sd is not None and self.z.mean is not None and atr is not None and v is not None:
                sig.ready = True
                z = (cum - self.z.mean) / sd if sd > 0 else 0.0
                vol_ok = bar.volume >= self.vol_mult * v if v > 0 else True
                above = vw is None or bar.close > vw
                below = vw is None or bar.close < vw
                sig.long_entry = z > self.z_entry and above and vol_ok
                sig.short_entry = z < -self.z_entry and below and vol_ok
                sig.exit_long = z < self.z_exit
                sig.exit_short = z > -self.z_exit
                sig.features = {"cum_delta": cum, "z": z}
        return self._finish(sig, atr)


class FundamentalMomentum(_Base):
    def __init__(self, preset: Preset, *, fundamentals_ok: bool = True) -> None:
        super().__init__(preset)
        p = self.params
        self.sma = Sma(int(p["sma_len"]))
        self.mom_len = int(p["mom_len"])
        self.mom_skip = int(p.get("mom_skip", 0))
        self.min_mom = float(p.get("min_mom_pct", 0.0))
        self.closes: deque[float] = deque(maxlen=self.mom_len + 1)
        self.fundamentals_ok = fundamentals_ok
        self._pc: float | None = None
        self._psma: float | None = None
        self.warmup = max(int(p["sma_len"]), self.mom_len) + 2

    def on_bar(self, bar: Bar) -> Signal:
        s = self.sma.update(bar.close)
        atr = self._atr.update(bar)
        self.closes.append(bar.close)
        sig = Signal()
        if s is not None and atr is not None and len(self.closes) == self.mom_len + 1:
            sig.ready = True
            ref = self.closes[0]
            recent = self.closes[-1 - self.mom_skip] if self.mom_skip < len(self.closes) else bar.close
            mom_pct = (recent / ref - 1.0) * 100.0 if ref > 0 else 0.0
            sig.long_entry = bar.close > s and mom_pct > self.min_mom and self.fundamentals_ok
            sig.exit_long = crossunder(self._pc, bar.close, self._psma, s)
            sig.features = {"sma": s, "momentum_pct": mom_pct}
        self._pc, self._psma = bar.close, s
        return self._finish(sig, atr)


def build_strategy(preset: Preset, *, fundamentals_ok: bool = True) -> Strategy:
    fam = preset.family
    if fam == "momentum_scalper":
        return MomentumScalper(preset)
    if fam == "mean_reversion_bands":
        return MeanReversionBands(preset)
    if fam == "breakout_donchian":
        return BreakoutDonchian(preset)
    if fam == "trend_supertrend_macd":
        return TrendSupertrendMacd(preset)
    if fam == "orderflow_imbalance":
        return OrderflowImbalance(preset)
    if fam == "fundamental_momentum":
        return FundamentalMomentum(preset, fundamentals_ok=fundamentals_ok)
    raise ValueError(f"unknown strategy family {fam!r}")
