"""Named TradingView strategy presets across horizons, timeframes, and markets.

A :class:`Preset` is the single source of truth for one algorithm: the
strategy family, its indicator parameters, the risk model (ATR stop / target /
time stop), the cost model (commission %, slippage ticks), the market it is
meant for, and the TradingView timeframe it was tuned on. Both the Pine
generator (:mod:`aoa.tradingview.pine`) and the offline emulator
(:mod:`aoa.tradingview.backtest`) read the same object, so the code you paste
into TradingView and the numbers you backtest here describe the same rules.

Horizons
--------
``hft``       sub-minute charts (1S/5S/15S) — crypto only; TradingView seconds
              charts need a Premium+ plan and bar magnifier for honest fills.
``scalp``     1–5 minute charts.
``intraday``  15–60 minute charts.
``swing``     4H / daily.
``position``  daily / weekly, fundamentals-gated (equities).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

# --------------------------------------------------------------------------- #
# Timeframes
# --------------------------------------------------------------------------- #

EQUITY_SESSION_SECONDS = int(6.5 * 3600)
EQUITY_DAYS_PER_YEAR = 252
CRYPTO_SECONDS_PER_YEAR = 365 * 24 * 3600


@dataclass(frozen=True)
class Timeframe:
    """One TradingView timeframe and its public-data provider equivalents."""

    key: str  # canonical key used in presets / CLI: "1S", "1", "5", "60", "1D", "1W"
    tv: str  # TradingView ``timeframe.period`` string
    seconds: int
    label: str
    yahoo: str | None = None  # Yahoo chart ``interval``
    yahoo_range: str | None = None  # Yahoo chart maximum ``range`` for that interval
    kraken: int | None = None  # Kraken OHLC ``interval`` (minutes)
    coinbase: int | None = None  # Coinbase Exchange ``granularity`` (seconds)

    @property
    def is_seconds(self) -> bool:
        return self.seconds < 60

    def bars_per_year(self, market: str) -> float:
        """Approximate bars per year for annualising bar returns."""
        if market == "crypto":
            return CRYPTO_SECONDS_PER_YEAR / self.seconds
        if self.seconds >= 7 * 86400:
            return 52.0
        if self.seconds >= 86400:
            return float(EQUITY_DAYS_PER_YEAR)
        return EQUITY_DAYS_PER_YEAR * (EQUITY_SESSION_SECONDS / self.seconds)


TIMEFRAMES: dict[str, Timeframe] = {
    tf.key: tf
    for tf in (
        Timeframe("1S", "1S", 1, "1 second"),
        Timeframe("5S", "5S", 5, "5 seconds"),
        Timeframe("15S", "15S", 15, "15 seconds"),
        Timeframe("30S", "30S", 30, "30 seconds"),
        Timeframe("1", "1", 60, "1 minute", yahoo="1m", yahoo_range="7d", kraken=1, coinbase=60),
        Timeframe("3", "3", 180, "3 minutes"),
        Timeframe("5", "5", 300, "5 minutes", yahoo="5m", yahoo_range="60d", kraken=5, coinbase=300),
        Timeframe(
            "15", "15", 900, "15 minutes", yahoo="15m", yahoo_range="60d", kraken=15, coinbase=900
        ),
        Timeframe("30", "30", 1800, "30 minutes", yahoo="30m", yahoo_range="60d", kraken=30),
        Timeframe("60", "60", 3600, "1 hour", yahoo="60m", yahoo_range="730d", kraken=60, coinbase=3600),
        Timeframe("240", "240", 14400, "4 hours", kraken=240),  # coinbase: resampled from 1h
        Timeframe("1D", "D", 86400, "1 day", yahoo="1d", yahoo_range="10y", kraken=1440, coinbase=86400),
        Timeframe("1W", "W", 7 * 86400, "1 week", yahoo="1wk", yahoo_range="20y", kraken=10080),
    )
}

_TF_ALIASES = {
    "1s": "1S",
    "5s": "5S",
    "15s": "15S",
    "30s": "30S",
    "1m": "1",
    "1min": "1",
    "3m": "3",
    "5m": "5",
    "5min": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "60m": "60",
    "1hour": "60",
    "4h": "240",
    "d": "1D",
    "1d": "1D",
    "day": "1D",
    "daily": "1D",
    "w": "1W",
    "1w": "1W",
    "week": "1W",
    "weekly": "1W",
}


def get_timeframe(key: str) -> Timeframe:
    k = key.strip()
    if k in TIMEFRAMES:
        return TIMEFRAMES[k]
    alias = _TF_ALIASES.get(k.lower())
    if alias:
        return TIMEFRAMES[alias]
    raise KeyError(f"Unknown timeframe {key!r}. Known: {', '.join(TIMEFRAMES)}")


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #

STRATEGY_FAMILIES: tuple[str, ...] = (
    "momentum_scalper",
    "mean_reversion_bands",
    "breakout_donchian",
    "trend_supertrend_macd",
    "orderflow_imbalance",
    "fundamental_momentum",
)

HORIZONS: tuple[str, ...] = ("hft", "scalp", "intraday", "swing", "position")
MARKETS: tuple[str, ...] = ("crypto", "equity")


@dataclass(frozen=True)
class RiskModel:
    """Deterministic exit rules shared by Pine and the emulator."""

    stop_atr: float = 1.5  # protective stop distance in ATR multiples (0 disables)
    target_atr: float = 2.5  # take-profit distance in ATR multiples (0 disables)
    trail_atr: float = 0.0  # ATR trailing stop (0 disables)
    max_bars_in_trade: int = 0  # time stop (0 disables)
    qty_pct_equity: float = 10.0  # percent of equity per position
    max_trades_per_day: int = 0  # 0 = unlimited
    session: str | None = None  # Pine session string for equities, e.g. "0935-1555"


@dataclass(frozen=True)
class CostModel:
    commission_pct: float = 0.05  # percent of notional per side
    slippage_ticks: int = 1  # TradingView ``slippage`` (ticks per fill)
    slippage_pct: float = 0.01  # emulator equivalent when tick size is unknown


@dataclass(frozen=True)
class FundamentalFilter:
    """Optional fundamentals gate (equities only)."""

    enabled: bool = False
    max_trailing_pe: float = 60.0
    min_eps_growth_pct: float = 0.0  # YoY basic EPS growth
    min_revenue_growth_pct: float = 0.0
    min_net_margin_pct: float = 0.0
    max_debt_to_equity: float = 3.0


@dataclass(frozen=True)
class Preset:
    name: str
    family: str
    horizon: str
    market: str
    timeframe: str
    description: str
    params: dict[str, Any] = field(default_factory=dict)
    risk: RiskModel = field(default_factory=RiskModel)
    costs: CostModel = field(default_factory=CostModel)
    fundamentals: FundamentalFilter = field(default_factory=FundamentalFilter)
    allow_short: bool = False
    use_bar_magnifier: bool = True
    tunable: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.family not in STRATEGY_FAMILIES:
            raise ValueError(f"unknown family {self.family!r}")
        if self.horizon not in HORIZONS:
            raise ValueError(f"unknown horizon {self.horizon!r}")
        if self.market not in MARKETS:
            raise ValueError(f"unknown market {self.market!r}")
        get_timeframe(self.timeframe)

    @property
    def tf(self) -> Timeframe:
        return get_timeframe(self.timeframe)

    def with_params(self, **overrides: Any) -> Preset:
        params = dict(self.params)
        params.update(overrides)
        return replace(self, params=params)

    def with_timeframe(self, timeframe: str) -> Preset:
        tf = get_timeframe(timeframe)
        return replace(self, timeframe=tf.key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "horizon": self.horizon,
            "market": self.market,
            "timeframe": self.timeframe,
            "timeframe_label": self.tf.label,
            "description": self.description,
            "params": dict(self.params),
            "risk": self.risk.__dict__.copy(),
            "costs": self.costs.__dict__.copy(),
            "fundamentals": self.fundamentals.__dict__.copy(),
            "allow_short": self.allow_short,
            "use_bar_magnifier": self.use_bar_magnifier,
            "tunable": {k: list(v) for k, v in self.tunable.items()},
            "tags": list(self.tags),
        }


_HFT_COSTS = CostModel(commission_pct=0.04, slippage_ticks=1, slippage_pct=0.01)
_SCALP_COSTS = CostModel(commission_pct=0.03, slippage_ticks=1, slippage_pct=0.01)
_SWING_COSTS = CostModel(commission_pct=0.02, slippage_ticks=1, slippage_pct=0.005)
_EQUITY_SESSION = "0935-1555"


def _momentum_params(fast: int, slow: int, rsi_len: int, rsi_floor: float, vol_mult: float) -> dict:
    return {
        "ema_fast": fast,
        "ema_slow": slow,
        "rsi_len": rsi_len,
        "rsi_floor": rsi_floor,
        "rsi_ceiling": 100.0 - rsi_floor + 20.0 if rsi_floor < 60 else 90.0,
        "atr_len": 14,
        "vol_len": 20,
        "vol_mult": vol_mult,
        "use_vwap": True,
    }


PRESETS: dict[str, Preset] = {
    p.name: p
    for p in (
        # ------------------------------------------------------------------ HFT
        Preset(
            name="hft-crypto-1s-momentum",
            family="momentum_scalper",
            horizon="hft",
            market="crypto",
            timeframe="1S",
            description=(
                "1-second EMA(5/13) micro-momentum with RSI(7) and VWAP side filter; "
                "1.0 ATR stop, 1.5 ATR target, 45-bar time stop. Crypto only — "
                "requires a TradingView plan with seconds charts and bar magnifier."
            ),
            params=_momentum_params(5, 13, 7, 52.0, 1.2) | {"atr_len": 7, "vol_len": 30},
            risk=RiskModel(stop_atr=1.0, target_atr=1.5, max_bars_in_trade=45, qty_pct_equity=15.0),
            costs=_HFT_COSTS,
            allow_short=True,
            tunable={"ema_fast": (3, 5, 8), "ema_slow": (13, 21), "rsi_floor": (50.0, 52.0, 55.0)},
            tags=("hft", "crypto", "momentum"),
        ),
        Preset(
            name="hft-crypto-5s-orderflow",
            family="orderflow_imbalance",
            horizon="hft",
            market="crypto",
            timeframe="5S",
            description=(
                "5-second bar-delta order-flow proxy: cumulative signed volume z-score "
                "above threshold with price above VWAP; tight ATR stop and time stop."
            ),
            params={
                "delta_len": 30,
                "z_entry": 1.6,
                "z_exit": 0.0,
                "atr_len": 10,
                "use_vwap": True,
                "vol_len": 30,
                "vol_mult": 1.0,
            },
            risk=RiskModel(stop_atr=1.2, target_atr=1.8, max_bars_in_trade=60, qty_pct_equity=15.0),
            costs=_HFT_COSTS,
            allow_short=True,
            tunable={"z_entry": (1.2, 1.6, 2.0), "delta_len": (20, 30, 50)},
            tags=("hft", "crypto", "orderflow"),
        ),
        Preset(
            name="hft-crypto-15s-meanrev",
            family="mean_reversion_bands",
            horizon="hft",
            market="crypto",
            timeframe="15S",
            description=(
                "15-second Bollinger(20, 2.0) reversion: fade closes beyond the bands "
                "when RSI(7) is stretched; exit at the basis or on stop."
            ),
            params={"bb_len": 20, "bb_mult": 2.0, "rsi_len": 7, "rsi_low": 25.0, "rsi_high": 75.0, "atr_len": 10},
            risk=RiskModel(stop_atr=1.5, target_atr=0.0, max_bars_in_trade=40, qty_pct_equity=12.0),
            costs=_HFT_COSTS,
            allow_short=True,
            tunable={"bb_mult": (1.8, 2.0, 2.4), "rsi_low": (20.0, 25.0, 30.0)},
            tags=("hft", "crypto", "mean-reversion"),
        ),
        # ---------------------------------------------------------------- SCALP
        Preset(
            name="scalp-crypto-1m-momentum",
            family="momentum_scalper",
            horizon="scalp",
            market="crypto",
            timeframe="1",
            description="1-minute EMA(8/21) momentum with RSI(9), VWAP side and volume surge filter.",
            params=_momentum_params(8, 21, 9, 52.0, 1.3),
            risk=RiskModel(stop_atr=1.2, target_atr=2.0, max_bars_in_trade=90, qty_pct_equity=12.0),
            costs=_SCALP_COSTS,
            allow_short=True,
            tunable={"ema_fast": (5, 8, 13), "ema_slow": (21, 34), "vol_mult": (1.0, 1.3, 1.6)},
            tags=("scalp", "crypto", "momentum"),
        ),
        Preset(
            name="scalp-equity-1m-momentum",
            family="momentum_scalper",
            horizon="scalp",
            market="equity",
            timeframe="1",
            description=(
                "1-minute long-only equity scalper: EMA(9/21) cross, RSI(9) > 52, above VWAP, "
                "volume surge; regular-session only, flat before the close."
            ),
            params=_momentum_params(9, 21, 9, 52.0, 1.5),
            risk=RiskModel(
                stop_atr=1.2, target_atr=2.0, max_bars_in_trade=60, qty_pct_equity=10.0,
                max_trades_per_day=6, session=_EQUITY_SESSION,
            ),
            costs=_SCALP_COSTS,
            tunable={"ema_fast": (5, 9, 13), "rsi_floor": (50.0, 52.0, 55.0)},
            tags=("scalp", "equity", "momentum", "long-only"),
        ),
        Preset(
            name="scalp-equity-5m-orderflow",
            family="orderflow_imbalance",
            horizon="scalp",
            market="equity",
            timeframe="5",
            description=(
                "5-minute bar-delta order-flow proxy for liquid US equities; long-only, "
                "regular session, cumulative-delta z-score entries above VWAP."
            ),
            params={"delta_len": 24, "z_entry": 1.5, "z_exit": 0.0, "atr_len": 14, "use_vwap": True, "vol_len": 20, "vol_mult": 1.1},
            risk=RiskModel(
                stop_atr=1.3, target_atr=2.2, max_bars_in_trade=36, qty_pct_equity=10.0,
                max_trades_per_day=4, session=_EQUITY_SESSION,
            ),
            costs=_SCALP_COSTS,
            tunable={"z_entry": (1.2, 1.5, 1.8), "delta_len": (12, 24, 36)},
            tags=("scalp", "equity", "orderflow", "long-only"),
        ),
        # ------------------------------------------------------------- INTRADAY
        Preset(
            name="intraday-equity-15m-breakout",
            family="breakout_donchian",
            horizon="intraday",
            market="equity",
            timeframe="15",
            description="15-minute Donchian(20) breakout with volume confirmation and 2 ATR trailing stop.",
            params={"channel_len": 20, "atr_len": 14, "vol_len": 20, "vol_mult": 1.2, "exit_channel_len": 10},
            risk=RiskModel(stop_atr=2.0, target_atr=0.0, trail_atr=2.0, max_bars_in_trade=0, qty_pct_equity=10.0, session=_EQUITY_SESSION),
            costs=_SWING_COSTS,
            tunable={"channel_len": (10, 20, 40), "vol_mult": (1.0, 1.2, 1.5)},
            tags=("intraday", "equity", "breakout", "long-only"),
        ),
        Preset(
            name="intraday-crypto-15m-supertrend",
            family="trend_supertrend_macd",
            horizon="intraday",
            market="crypto",
            timeframe="15",
            description="15-minute Supertrend(10, 3) direction confirmed by MACD(12/26/9) histogram sign.",
            params={"st_len": 10, "st_mult": 3.0, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "atr_len": 14},
            risk=RiskModel(stop_atr=2.0, target_atr=0.0, trail_atr=0.0, qty_pct_equity=12.0),
            costs=_SWING_COSTS,
            allow_short=True,
            tunable={"st_mult": (2.0, 3.0, 4.0), "st_len": (7, 10, 14)},
            tags=("intraday", "crypto", "trend"),
        ),
        # ---------------------------------------------------------------- SWING
        Preset(
            name="swing-equity-1h-supertrend",
            family="trend_supertrend_macd",
            horizon="swing",
            market="equity",
            timeframe="60",
            description="1-hour Supertrend(10, 3) + MACD histogram trend follower for US equities (long-only).",
            params={"st_len": 10, "st_mult": 3.0, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "atr_len": 14},
            risk=RiskModel(stop_atr=2.5, target_atr=0.0, qty_pct_equity=10.0),
            costs=_SWING_COSTS,
            tunable={"st_mult": (2.5, 3.0, 3.5)},
            tags=("swing", "equity", "trend", "long-only"),
        ),
        Preset(
            name="swing-equity-4h-breakout",
            family="breakout_donchian",
            horizon="swing",
            market="equity",
            timeframe="240",
            description="4-hour Donchian(30) breakout with 2.5 ATR trailing stop.",
            params={"channel_len": 30, "atr_len": 14, "vol_len": 20, "vol_mult": 1.0, "exit_channel_len": 15},
            risk=RiskModel(stop_atr=2.5, target_atr=0.0, trail_atr=2.5, qty_pct_equity=10.0),
            costs=_SWING_COSTS,
            tunable={"channel_len": (20, 30, 55)},
            tags=("swing", "equity", "breakout", "long-only"),
        ),
        Preset(
            name="swing-crypto-4h-momentum",
            family="momentum_scalper",
            horizon="swing",
            market="crypto",
            timeframe="240",
            description="4-hour EMA(21/55) momentum for crypto majors with RSI(14) confirmation.",
            params=_momentum_params(21, 55, 14, 50.0, 1.0) | {"use_vwap": False},
            risk=RiskModel(stop_atr=2.0, target_atr=4.0, max_bars_in_trade=0, qty_pct_equity=15.0),
            costs=_SWING_COSTS,
            allow_short=True,
            tunable={"ema_fast": (13, 21), "ema_slow": (55, 89)},
            tags=("swing", "crypto", "momentum"),
        ),
        Preset(
            name="swing-equity-1d-trend",
            family="trend_supertrend_macd",
            horizon="swing",
            market="equity",
            timeframe="1D",
            description=(
                "Daily Supertrend(10, 3) + MACD(12/26/9) histogram trend follower for US equities "
                "(long-only, 2.5 ATR stop). The workhorse for the 2000-stock universe sweep."
            ),
            params={"st_len": 10, "st_mult": 3.0, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "atr_len": 14},
            risk=RiskModel(stop_atr=2.5, target_atr=0.0, qty_pct_equity=10.0),
            costs=_SWING_COSTS,
            tunable={"st_mult": (2.0, 3.0, 4.0), "atr_len": (10, 14)},
            tags=("swing", "equity", "trend", "long-only", "universe"),
        ),
        Preset(
            name="swing-equity-1d-breakout",
            family="breakout_donchian",
            horizon="swing",
            market="equity",
            timeframe="1D",
            description="Daily Donchian(55) breakout with volume confirmation and 3 ATR trailing stop (long-only).",
            params={"channel_len": 55, "atr_len": 20, "vol_len": 20, "vol_mult": 1.0, "exit_channel_len": 20},
            risk=RiskModel(stop_atr=3.0, target_atr=0.0, trail_atr=3.0, qty_pct_equity=10.0),
            costs=_SWING_COSTS,
            tunable={"channel_len": (20, 55, 100), "exit_channel_len": (10, 20)},
            tags=("swing", "equity", "breakout", "long-only", "universe"),
        ),
        Preset(
            name="swing-crypto-1d-meanrev",
            family="mean_reversion_bands",
            horizon="swing",
            market="crypto",
            timeframe="1D",
            description="Daily Bollinger(20, 2) reversion for crypto: buy band breaks with RSI(14) < 30, exit at the basis.",
            params={"bb_len": 20, "bb_mult": 2.0, "rsi_len": 14, "rsi_low": 30.0, "rsi_high": 70.0, "atr_len": 14},
            risk=RiskModel(stop_atr=2.0, target_atr=0.0, max_bars_in_trade=15, qty_pct_equity=15.0),
            costs=_SWING_COSTS,
            tunable={"bb_mult": (1.8, 2.0, 2.5), "rsi_low": (25.0, 30.0, 35.0)},
            tags=("swing", "crypto", "mean-reversion"),
        ),
        # ------------------------------------------------------------- POSITION
        Preset(
            name="position-crypto-1d-trend",
            family="trend_supertrend_macd",
            horizon="position",
            market="crypto",
            timeframe="1D",
            description="Daily Supertrend(10, 3) + MACD for BTC/ETH majors; long/short.",
            params={"st_len": 10, "st_mult": 3.0, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "atr_len": 14},
            risk=RiskModel(stop_atr=3.0, target_atr=0.0, qty_pct_equity=20.0),
            costs=_SWING_COSTS,
            allow_short=True,
            tunable={"st_mult": (2.0, 3.0, 4.0)},
            tags=("position", "crypto", "trend"),
        ),
        Preset(
            name="position-equity-1d-fundamental",
            family="fundamental_momentum",
            horizon="position",
            market="equity",
            timeframe="1D",
            description=(
                "Daily 12-1 momentum above the 200-day SMA, gated by fundamentals "
                "(trailing P/E cap, positive EPS and revenue growth); 3 ATR trailing stop."
            ),
            params={"sma_len": 200, "mom_len": 252, "mom_skip": 21, "atr_len": 14, "min_mom_pct": 5.0},
            risk=RiskModel(stop_atr=3.0, target_atr=0.0, trail_atr=3.0, qty_pct_equity=10.0),
            costs=_SWING_COSTS,
            fundamentals=FundamentalFilter(enabled=True, max_trailing_pe=45.0, min_eps_growth_pct=0.0, min_revenue_growth_pct=0.0),
            tunable={"sma_len": (100, 150, 200), "min_mom_pct": (0.0, 5.0, 10.0)},
            tags=("position", "equity", "fundamental", "momentum", "long-only"),
        ),
        Preset(
            name="position-equity-1w-fundamental",
            family="fundamental_momentum",
            horizon="position",
            market="equity",
            timeframe="1W",
            description="Weekly 52-week momentum above the 40-week SMA, fundamentals-gated, 3 ATR trailing stop.",
            params={"sma_len": 40, "mom_len": 52, "mom_skip": 4, "atr_len": 10, "min_mom_pct": 5.0},
            risk=RiskModel(stop_atr=3.0, target_atr=0.0, trail_atr=3.0, qty_pct_equity=10.0),
            costs=_SWING_COSTS,
            fundamentals=FundamentalFilter(enabled=True, max_trailing_pe=45.0, min_eps_growth_pct=0.0, min_revenue_growth_pct=0.0, min_net_margin_pct=5.0),
            tunable={"sma_len": (30, 40, 50)},
            tags=("position", "equity", "fundamental", "momentum", "long-only"),
        ),
    )
}


def get_preset(name: str) -> Preset:
    try:
        return PRESETS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown preset {name!r}. Known: {', '.join(sorted(PRESETS))}") from exc


def list_presets(
    *,
    horizon: str | None = None,
    market: str | None = None,
    family: str | None = None,
) -> list[Preset]:
    out = []
    for p in PRESETS.values():
        if horizon and p.horizon != horizon:
            continue
        if market and p.market != market:
            continue
        if family and p.family != family:
            continue
        out.append(p)
    return out
