#!/usr/bin/env python3
"""Run upstream TradingAgentsGraph.propagate() for a symbol and trade date.

This script wraps the official TauricResearch TradingAgents library
(https://github.com/TauricResearch/TradingAgents) for offline / historical
decision propagation. It is separate from AOA's live Alpaca swarm pipeline.

Install the optional extra first (pins upstream v0.3.0):
  pip install -e ".[tradingagents]"
  pip install -e ".[tradingagents-bedrock]"   # optional AWS Bedrock provider

Upstream changelog: docs/tradingagents/CHANGELOG.md

Configuration:
  TRADINGAGENTS_* env vars override DEFAULT_CONFIG (see upstream default_config.py).
  AOA's .env / profiles are loaded first so you can keep secrets in one place.

Examples:
  python scripts/tradingagents_propagate.py NVDA 2024-05-10
  python scripts/tradingagents_propagate.py AAPL 2024-05-10 --debug
  python scripts/tradingagents_propagate.py NVDA 2024-05-10 --reflect 0.12
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def _load_aoa_env() -> None:
    """Load AOA profiles/.env before upstream reads TRADINGAGENTS_* vars."""
    try:
        from aoa.config import load_env_files

        load_env_files()
    except ImportError:
        pass


def _ensure_upstream_importable() -> None:
    try:
        import tradingagents  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "The upstream 'tradingagents' package is not installed.\n"
            "Install with: pip install -e \".[tradingagents]\"\n"
            "Or clone https://github.com/TauricResearch/TradingAgents and pip install .\n"
            f"Original error: {exc}"
        ) from exc


def _map_aoa_anthropic_defaults() -> None:
    """Bridge common AOA .env keys when TRADINGAGENTS_* are unset."""
    if not os.environ.get("TRADINGAGENTS_LLM_PROVIDER"):
        if os.environ.get("ANTHROPIC_API_KEY"):
            os.environ.setdefault("TRADINGAGENTS_LLM_PROVIDER", "anthropic")
    if not os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM"):
        model = os.environ.get("AOA_MODEL")
        if model:
            os.environ.setdefault("TRADINGAGENTS_DEEP_THINK_LLM", model)
            os.environ.setdefault("TRADINGAGENTS_QUICK_THINK_LLM", model)
    if not os.environ.get("TRADINGAGENTS_ANTHROPIC_EFFORT"):
        effort = os.environ.get("AOA_EFFORT")
        if effort:
            os.environ.setdefault("TRADINGAGENTS_ANTHROPIC_EFFORT", effort)
    if not os.environ.get("TRADINGAGENTS_MAX_DEBATE_ROUNDS"):
        rounds = os.environ.get("AOA_TRADING_AGENTS_DEBATE_ROUNDS")
        if rounds:
            os.environ.setdefault("TRADINGAGENTS_MAX_DEBATE_ROUNDS", rounds)


def _print_decision(decision: Any) -> None:
    if isinstance(decision, dict):
        print(json.dumps(decision, indent=2, default=str))
        return
    print(decision)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="Ticker symbol, e.g. NVDA")
    parser.add_argument("trade_date", help="Trade date YYYY-MM-DD, e.g. 2024-05-10")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable TradingAgentsGraph debug output.",
    )
    parser.add_argument(
        "--reflect",
        type=float,
        metavar="RETURN",
        help="After propagate, call reflect_and_remember with position return.",
    )
    parser.add_argument(
        "--config-json",
        help="Optional path to JSON file merged into DEFAULT_CONFIG.",
    )
    args = parser.parse_args(argv)

    _load_aoa_env()
    _map_aoa_anthropic_defaults()
    _ensure_upstream_importable()

    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    try:
        import importlib.metadata as importlib_metadata
    except ImportError:
        import importlib_metadata  # type: ignore[no-redef]

    try:
        upstream_version = importlib_metadata.version("tradingagents")
    except importlib_metadata.PackageNotFoundError:
        upstream_version = "unknown"

    config = DEFAULT_CONFIG.copy()
    if args.config_json:
        import pathlib

        extra = json.loads(pathlib.Path(args.config_json).read_text(encoding="utf-8"))
        if not isinstance(extra, dict):
            raise SystemExit("--config-json must contain a JSON object.")
        config.update(extra)

    symbol = args.symbol.upper().strip()
    trade_date = args.trade_date.strip()

    print(f"TradingAgents propagate: {symbol} @ {trade_date}")
    print(f"upstream tradingagents=={upstream_version}")
    print(
        f"provider={config.get('llm_provider')} "
        f"deep={config.get('deep_think_llm')} "
        f"quick={config.get('quick_think_llm')}"
    )

    ta = TradingAgentsGraph(debug=args.debug, config=config)
    _, decision = ta.propagate(symbol, trade_date)
    print("\n=== Decision ===")
    _print_decision(decision)

    if args.reflect is not None:
        print(f"\n=== Reflect (return={args.reflect}) ===")
        ta.reflect_and_remember(args.reflect)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
