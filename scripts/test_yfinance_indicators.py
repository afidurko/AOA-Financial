#!/usr/bin/env python3
"""Benchmark upstream TradingAgents yfinance technical indicator window.

Exercises ``get_stock_stats_indicators_window`` from the official TauricResearch
TradingAgents library (https://github.com/TauricResearch/TradingAgents). This is
separate from AOA's live Alpaca swarm pipeline.

Install the optional extra first (pins upstream v0.3.0):
  pip install -e ".[tradingagents]"

Upstream changelog: docs/tradingagents/CHANGELOG.md

Examples:
  python scripts/test_yfinance_indicators.py AAPL macd 2024-11-01
  python scripts/test_yfinance_indicators.py NVDA rsi 2024-05-10 --lookback 14
  python scripts/test_yfinance_indicators.py AAPL macd 2024-11-01 --require-extra

Exits 0 when the call succeeds. Skips gracefully (exit 0) when the
``tradingagents`` extra is not installed unless ``--require-extra`` is passed.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time


def _upstream_installed() -> bool:
    return importlib.util.find_spec("tradingagents") is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="Ticker symbol, e.g. AAPL")
    parser.add_argument(
        "indicator",
        help="Stockstats indicator name, e.g. macd, rsi, close_50_sma",
    )
    parser.add_argument("trade_date", help="End date YYYY-MM-DD, e.g. 2024-11-01")
    parser.add_argument(
        "--lookback",
        type=int,
        default=30,
        metavar="DAYS",
        help="Trading-day lookback window (default: 30).",
    )
    parser.add_argument(
        "--require-extra",
        action="store_true",
        help="Exit 1 when tradingagents is not installed (default: skip with exit 0).",
    )
    args = parser.parse_args(argv)

    if not _upstream_installed():
        msg = (
            "The upstream 'tradingagents' package is not installed — "
            "skipping yfinance indicator benchmark.\n"
            "Install with: pip install -e \".[tradingagents]\""
        )
        print(msg)
        return 1 if args.require_extra else 0

    from tradingagents.dataflows.y_finance import get_stock_stats_indicators_window

    symbol = args.symbol.upper().strip()
    indicator = args.indicator.strip().lower()
    trade_date = args.trade_date.strip()
    lookback = args.lookback

    print(
        f"Testing optimized implementation with {lookback}-day lookback: "
        f"{symbol} / {indicator} @ {trade_date}"
    )
    start_time = time.time()
    result = get_stock_stats_indicators_window(symbol, indicator, trade_date, lookback)
    elapsed = time.time() - start_time

    print(f"Execution time: {elapsed:.2f} seconds")
    print(f"Result length: {len(result)} characters")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
