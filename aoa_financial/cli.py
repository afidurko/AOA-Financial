"""Command-line interface for AOA-Financial.

Subcommands:

    init        Create the database and ingest the default universe.
    ingest      Ingest one or more tickers (synthetic or live).
    analyze     Full deep analysis + swarm decision for a ticker.
    forecast    Probabilistic price forecast for a ticker.
    regime      Current inferred market regime for a ticker.
    reverse     Reverse-engineer the drivers of a ticker's trend.
    swarm       Run the swarm across many tickers and rank decisions.
    demo        End-to-end demonstration on a few tickers.

Run ``python -m aoa_financial <command> --help`` for details.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import List, Optional

from .config import Config
from .databases.store import MarketStore
from .ingest.loaders import ingest_ticker, ingest_universe
from .analysis import forecast as FC
from .analysis import regimes as RG
from .analysis.reverse_engineer import reverse_engineer
from .swarm.decision import analyze_ticker


def _store(config: Config) -> MarketStore:
    config.ensure_dirs()
    return MarketStore(config.db_path)


def _ensure_ingested(store: MarketStore, ticker: str, prefer_live: bool) -> None:
    if not store.has_prices(ticker):
        ingest_ticker(store, ticker, prefer_live=prefer_live)


# -- command handlers -----------------------------------------------------
def cmd_init(args, config: Config) -> int:
    with _store(config) as store:
        reports = ingest_universe(store, config.default_universe,
                                  prefer_live=args.live)
        total = sum(r["bars"] for r in reports)
        print(f"Initialised {config.db_path}")
        print(f"Ingested {len(reports)} securities, {total:,} total bars "
              f"(since {config.epoch_start}).")
        for r in reports:
            print(f"  {r['ticker']:6s} {r['source']:9s} {r['bars']:>6,} bars  "
                  f"[{r['sector']}]")
    return 0


def cmd_ingest(args, config: Config) -> int:
    with _store(config) as store:
        for t in args.tickers:
            r = ingest_ticker(store, t, prefer_live=args.live, refresh=args.refresh)
            print(f"{r['ticker']:6s} {r['source']:9s} {r['bars']:>6,} bars  "
                  f"[{r['sector']}]" + ("  (cached)" if r.get("cached") else ""))
    return 0


def cmd_analyze(args, config: Config) -> int:
    with _store(config) as store:
        _ensure_ingested(store, args.ticker, args.live)
        decision = analyze_ticker(store, args.ticker, config=config,
                                  horizon=args.horizon,
                                  use_llm=not args.no_llm, persist=not args.no_persist)
        if args.json:
            print(json.dumps(decision.to_dict(), indent=2))
        else:
            _print_decision(decision)
    return 0


def cmd_forecast(args, config: Config) -> int:
    with _store(config) as store:
        _ensure_ingested(store, args.ticker, args.live)
        closes = store.closes(args.ticker)
        f = FC.forecast(closes, horizon_days=args.horizon)
        print(json.dumps(f.to_dict(), indent=2) if args.json else _fmt_forecast(args.ticker, f))
    return 0


def cmd_regime(args, config: Config) -> int:
    with _store(config) as store:
        _ensure_ingested(store, args.ticker, args.live)
        bars = store.get_bars(args.ticker)
        state = RG.classify(bars)
        print(json.dumps(state.to_dict(), indent=2) if args.json else
              f"{args.ticker}: regime={state.regime} "
              f"(confidence {state.confidence:.0%}), "
              f"annualised vol {state.annualized_vol:.0%}, "
              f"trend {state.trend_strength:+.0%}/yr, "
              f"drawdown {state.drawdown:.0%}")
    return 0


def cmd_reverse(args, config: Config) -> int:
    with _store(config) as store:
        _ensure_ingested(store, args.ticker, args.live)
        bars = store.get_bars(args.ticker)
        res = reverse_engineer(args.ticker, bars,
                               stored_sentiment=store.latest_sentiment(args.ticker))
        if args.json:
            print(json.dumps(res.to_dict(), indent=2))
        else:
            _print_reverse(res)
    return 0


def cmd_frame(args, config: Config) -> int:
    from .analysis import frames
    if not frames.HAS_PANDAS:
        print("pandas not installed. Run: pip install pandas", file=sys.stderr)
        return 1
    with _store(config) as store:
        _ensure_ingested(store, args.ticker, args.live)
        df = frames.indicator_frame(frames.store_frame(store, args.ticker))
        if args.csv:
            df.to_csv(args.csv)
            print(f"wrote {len(df):,} rows x {df.shape[1]} cols -> {args.csv}")
        else:
            cols = ["close", "sma_50", "sma_200", "rsi_14", "macd_hist",
                    "bb_pct_b", "atr_14", "vol_252", "drawdown"]
            import pandas as pd
            with pd.option_context("display.width", 160,
                                   "display.max_columns", None):
                print(df[cols].tail(args.tail).round(3))
    return 0


def cmd_corr(args, config: Config) -> int:
    from .analysis import frames
    if not frames.HAS_PANDAS:
        print("pandas not installed. Run: pip install pandas", file=sys.stderr)
        return 1
    tickers = args.tickers or config.default_universe
    with _store(config) as store:
        for t in tickers:
            _ensure_ingested(store, t, args.live)
        corr = frames.correlation_matrix(store, tickers, window=args.window)
        if args.csv:
            corr.to_csv(args.csv)
            print(f"wrote correlation matrix -> {args.csv}")
        else:
            print(f"Return correlation (last {args.window} sessions):\n")
            print(corr.round(2))
    return 0


def cmd_swarm(args, config: Config) -> int:
    tickers = args.tickers or config.default_universe
    run_id = f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    decisions = []
    with _store(config) as store:
        for t in tickers:
            _ensure_ingested(store, t, args.live)
            try:
                d = analyze_ticker(store, t, config=config, horizon=args.horizon,
                                   use_llm=not args.no_llm, run_id=run_id,
                                   persist=not args.no_persist)
                decisions.append(d)
            except ValueError as e:
                print(f"  skip {t}: {e}", file=sys.stderr)
    decisions.sort(key=lambda d: d.conviction, reverse=True)
    if args.json:
        print(json.dumps([d.to_dict() for d in decisions], indent=2))
    else:
        print(f"\nSwarm ranking ({run_id}) — {len(decisions)} names\n" + "=" * 64)
        print(f"{'TICKER':8s}{'ACTION':7s}{'CONV':>7s}{'CONF':>7s}{'WEIGHT':>8s}  RATIONALE")
        for d in decisions:
            print(f"{d.ticker:8s}{d.action:7s}{d.conviction:>+7.2f}"
                  f"{d.confidence:>7.0%}{d.target_weight:>8.1%}  "
                  f"{d.rationale[:60]}")
    return 0


def cmd_demo(args, config: Config) -> int:
    tickers = args.tickers or ["AAPL", "XOM", "JPM"]
    print("AOA-Financial demonstration")
    print("=" * 64)
    with _store(config) as store:
        for t in tickers:
            r = ingest_ticker(store, t, prefer_live=args.live)
            sec = store.get_security(t)
            since = sec.listed_on if sec else "?"
            print(f"\n[{t}] {r['bars']:,} bars since {since} [{r['sector']}]")
            d = analyze_ticker(store, t, config=config, use_llm=not args.no_llm)
            _print_decision(d, compact=True)
    print("\nDone. Data + decisions persisted to", config.db_path)
    return 0


# -- pretty printers ------------------------------------------------------
def _print_decision(d, compact: bool = False) -> None:
    print(f"\n=== {d.ticker} — {d.action} ===")
    print(f"as of {d.asof} | conviction {d.conviction:+.2f} | "
          f"confidence {d.confidence:.0%} | suggested weight {d.target_weight:.1%}")
    print(d.rationale)
    print("\nAgent signals:")
    for s in d.signals:
        print(f"  {s.agent:12s} {s.action:5s} score={s.score:+.2f} "
              f"conf={s.confidence:.0%}  {s.rationale[:54]}")
    if not compact:
        analyst = d.evidence.get("analyst")
        if analyst:
            print(f"\nAnalyst ({analyst['source']}): {analyst['thesis'][:400]}")


def _fmt_forecast(ticker, f) -> str:
    return (f"{ticker} {f.horizon_days}d forecast: last {f.last_price:.2f} -> "
            f"expected {f.expected_price:.2f} ({f.expected_return:+.1%}, "
            f"{f.direction}), confidence {f.confidence:.0%}\n"
            f"  cone p10/p50/p90: {f.p10:.2f} / {f.p50:.2f} / {f.p90:.2f}")


def _print_reverse(res) -> None:
    print(f"\nReverse-engineering: {res.ticker}")
    print(f"  explained variance (R²): {res.explained_variance:.2f}")
    print(f"  dominant drivers: {', '.join(res.dominant_drivers)}")
    print(f"  trend {res.trend_component:+.0%}/yr | risk {res.risk_component:.0%} "
          f"| trend/risk {res.drift_to_risk:+.2f}")
    print(f"  regime: {res.regime} ({res.regime_confidence:.0%}) | "
          f"sentiment {res.sentiment:+.2f} | forward bias {res.forward_bias:+.2f}")
    print("  inferences:")
    for i in res.inferences:
        print(f"    - {i}")
    print("  assumptions:")
    for a in res.assumptions:
        print(f"    - {a}")


# -- argument parsing -----------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aoa_financial",
                                description="Deep stock analysis, forecasting "
                                            "and swarm decision engine.")
    p.add_argument("--data-dir", help="override data directory")
    p.add_argument("--live", action="store_true",
                   help="prefer live data (Stooq) before synthetic fallback")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp, ticker=False, tickers=False):
        sp.add_argument("--json", action="store_true", help="emit JSON")
        sp.add_argument("--horizon", type=int, default=21,
                        help="forecast horizon in trading days")
        sp.add_argument("--no-llm", action="store_true",
                        help="skip the LLM analyst agent")
        sp.add_argument("--no-persist", action="store_true",
                        help="do not write results to the database")
        if ticker:
            sp.add_argument("ticker", help="ticker symbol")
        if tickers:
            sp.add_argument("tickers", nargs="*", help="ticker symbols")

    sp = sub.add_parser("init", help="create DB and ingest default universe")
    sp = sub.add_parser("ingest", help="ingest tickers")
    sp.add_argument("tickers", nargs="+")
    sp.add_argument("--refresh", action="store_true", help="re-fetch even if cached")

    add_common(sub.add_parser("analyze", help="full deep analysis + decision"),
               ticker=True)
    add_common(sub.add_parser("forecast", help="probabilistic forecast"),
               ticker=True)
    add_common(sub.add_parser("regime", help="infer current regime"), ticker=True)
    add_common(sub.add_parser("reverse", help="reverse-engineer trend drivers"),
               ticker=True)
    sp = sub.add_parser("frame", help="vectorised indicator panel (pandas)")
    sp.add_argument("ticker")
    sp.add_argument("--tail", type=int, default=10, help="rows to display")
    sp.add_argument("--csv", help="write the full indicator frame to a CSV path")

    sp = sub.add_parser("corr", help="return-correlation matrix (pandas)")
    sp.add_argument("tickers", nargs="*")
    sp.add_argument("--window", type=int, default=252,
                    help="lookback in trading days")
    sp.add_argument("--csv", help="write the matrix to a CSV path")

    add_common(sub.add_parser("swarm", help="rank decisions across tickers"),
               tickers=True)
    add_common(sub.add_parser("demo", help="end-to-end demonstration"),
               tickers=True)
    return p


_HANDLERS = {
    "init": cmd_init, "ingest": cmd_ingest, "analyze": cmd_analyze,
    "forecast": cmd_forecast, "regime": cmd_regime, "reverse": cmd_reverse,
    "frame": cmd_frame, "corr": cmd_corr,
    "swarm": cmd_swarm, "demo": cmd_demo,
}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = Config()
    if getattr(args, "data_dir", None):
        config = Config(data_dir=args.data_dir)
    # `ingest` lacks the common flags; normalise.
    for attr in ("live",):
        if not hasattr(args, attr):
            setattr(args, attr, False)
    return _HANDLERS[args.command](args, config)


if __name__ == "__main__":
    raise SystemExit(main())
