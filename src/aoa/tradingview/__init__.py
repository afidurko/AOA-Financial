"""TradingView desk — Pine v6 strategy presets, offline backtests, neural memory.

This lane turns AOA's research into artifacts a human can paste into
TradingView (Pine Script v6 ``strategy()`` scripts) and validates the *same*
rules offline with a bar-level broker emulator that mirrors TradingView's
fill assumptions (next-bar-open fills, OHLC intrabar stop/target checks,
percent-of-equity sizing, percent commission, tick slippage).

Sub-modules:

* :mod:`aoa.tradingview.presets`     — named presets (HFT / scalp / intraday /
  swing / position) across TradingView timeframes for crypto and US equities.
* :mod:`aoa.tradingview.rules`       — incremental indicator kernels and the
  strategy families' bar-by-bar signal logic (Python reference implementation).
* :mod:`aoa.tradingview.pine`        — Pine Script v6 generator for every preset.
* :mod:`aoa.tradingview.backtest`    — broker emulator, metrics, walk-forward,
  parameter sweeps, Monte-Carlo trade shuffles.
* :mod:`aoa.tradingview.data`        — Yahoo / Kraken / Coinbase public candles
  with a CSV cache and a seeded synthetic fallback.
* :mod:`aoa.tradingview.universe`    — ~2000-name US equity universe across
  NASDAQ / NYSE / NYSE American / NYSE Arca / Cboe from Nasdaq Trader files.
* :mod:`aoa.tradingview.fundamentals`— fundamental gate (P/E, growth, margins).
* :mod:`aoa.tradingview.memory`      — persistent neural memory (Hebbian trust
  mesh over presets × symbols × timeframes) shared by the desk agents.
* :mod:`aoa.tradingview.connectome`  — fly-brain connectome mapping (sensory →
  Kenyon cells → mushroom body / dopamine → central complex → descending
  neurons → motor) that turns evidence into *proposed* motor commands. The
  human always has the final say; nothing here places orders.
* :mod:`aoa.tradingview.desk`        — the TradingView desk sub-team runner.

Nothing in this package talks to a broker. ``never_live`` is structural.
"""

from aoa.tradingview.presets import PRESETS, Preset, get_preset, list_presets

__all__ = ["PRESETS", "Preset", "get_preset", "list_presets"]
