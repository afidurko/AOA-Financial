"""``aoa tradingview`` — CLI surface for the TradingView desk (offline; no orders)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from aoa.tradingview.backtest import EmulatorConfig, monte_carlo_trades, run_backtest, walk_forward
from aoa.tradingview.connectome import DN_CHANNELS, REGIONS, FlyConnectome, MarketSense
from aoa.tradingview.data import SOURCES, fetch_bars, guess_market
from aoa.tradingview.desk import DESK_LEAD, DESK_MEMBERS, DESK_REVIEW, DESK_RISK, DeskRunner
from aoa.tradingview.fundamentals import YahooFundamentals, gate_passes
from aoa.tradingview.memory import DeskMemory
from aoa.tradingview.pine import generate_pine, lint_pine, pine_filename
from aoa.tradingview.presets import HORIZONS, MARKETS, PRESETS, TIMEFRAMES, get_preset, list_presets
from aoa.tradingview.universe import load_universe


def _csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def add_tradingview_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    tv = sub.add_parser(
        "tradingview",
        aliases=["tv"],
        help="TradingView desk: Pine v6 presets, offline backtests, neural memory, connectome (no orders).",
    )
    tv_sub = tv.add_subparsers(dest="tradingview_command", required=True)

    p = tv_sub.add_parser("presets", help="List strategy presets.")
    p.add_argument("--horizon", choices=HORIZONS)
    p.add_argument("--market", choices=MARKETS)
    p.add_argument("--json", action="store_true")

    p = tv_sub.add_parser("pine", help="Generate Pine Script v6 for a preset (or --all).")
    p.add_argument("preset", nargs="?", help="Preset name (see: aoa tradingview presets).")
    p.add_argument("--all", action="store_true", help="Write every preset to --dir.")
    p.add_argument("--dir", default="tradingview", help="Output directory for --all (default: tradingview/).")
    p.add_argument("--out", help="Write a single preset to this file instead of stdout.")
    p.add_argument("--timeframe", help="Override the preset timeframe (e.g. 5, 60, 1D).")

    p = tv_sub.add_parser("backtest", help="Backtest one preset on one symbol with TradingView fill semantics.")
    p.add_argument("preset")
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", help="Override preset timeframe.")
    p.add_argument("--source", choices=SOURCES, default="auto")
    p.add_argument("--limit", type=int, help="Use only the most recent N bars.")
    p.add_argument("--folds", type=int, default=0, help="Walk-forward folds (0 = skip).")
    p.add_argument("--monte-carlo", action="store_true", help="Add trade-shuffle Monte-Carlo.")
    p.add_argument("--seed", type=int, help="Synthetic data seed.")
    p.add_argument("--trades", action="store_true", help="Print every trade.")
    p.add_argument("--json", action="store_true")

    p = tv_sub.add_parser("desk", help="Run / inspect the TradingView desk sub-team.")
    d_sub = p.add_subparsers(dest="desk_command", required=True)
    d_run = d_sub.add_parser("run", help="Full desk cycle: fetch → backtest → learn → propose → report.")
    d_run.add_argument("--symbols", required=True, help="Comma-separated symbols (AAPL,BTC-USD,…).")
    d_run.add_argument("--presets", help="Comma-separated preset names (default: all matching the market).")
    d_run.add_argument("--timeframes", help="Comma-separated timeframes to test each preset on (default: preset's own).")
    d_run.add_argument("--source", choices=SOURCES, default="auto")
    d_run.add_argument("--limit", type=int)
    d_run.add_argument("--folds", type=int, default=3)
    d_run.add_argument("--no-monte-carlo", action="store_true")
    d_run.add_argument("--workers", type=int, default=1)
    d_run.add_argument("--pause", type=float, default=0.0, help="Seconds to sleep between network fetches.")
    d_run.add_argument("--seed", type=int)
    d_run.add_argument("--export-pine", action="store_true", help="Also write Pine files for the presets used.")
    d_run.add_argument("--no-fundamentals", action="store_true")
    d_run.add_argument("--json", action="store_true")
    d_sub.add_parser("status", help="Desk roster, memory summary, last report.").add_argument("--json", action="store_true")

    p = tv_sub.add_parser("universe", help="Build the US equity universe (~2000 names across exchanges).")
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--exchanges", help="Comma-separated: NASDAQ,NYSE,NYSE American,NYSE Arca,Cboe BZX,IEX")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--csv", help="Write the universe to a CSV file.")
    p.add_argument("--json", action="store_true")

    p = tv_sub.add_parser("universe-sweep", help="Batch-run one preset across the universe (resumable, cached).")
    p.add_argument("--preset", default="position-equity-1d-fundamental")
    p.add_argument("--timeframe", help="Override preset timeframe (default: preset's own).")
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=50, help="Symbols per batch.")
    p.add_argument("--exchanges")
    p.add_argument("--source", choices=SOURCES, default="auto")
    p.add_argument("--pause", type=float, default=0.4)
    p.add_argument("--folds", type=int, default=2)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--no-fundamentals", action="store_true")
    p.add_argument("--json", action="store_true")

    p = tv_sub.add_parser("memory", help="Inspect the desk's neural memory.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--edges", type=int, default=10)

    p = tv_sub.add_parser("connectome", help="Fly-brain connectome mapping status / manual probe.")
    c_sub = p.add_subparsers(dest="connectome_command", required=True)
    c_sub.add_parser("status", help="Region map, DN channels, learned valence.").add_argument("--json", action="store_true")
    c_step = c_sub.add_parser("step", help="Probe one sensory vector → motor proposal (no orders).")
    c_step.add_argument("--symbol", default="PROBE")
    c_step.add_argument("--trend", type=float, default=0.0)
    c_step.add_argument("--momentum", type=float, default=0.0)
    c_step.add_argument("--orderflow", type=float, default=0.0)
    c_step.add_argument("--volatility", type=float, default=0.2)
    c_step.add_argument("--drawdown", type=float, default=0.0)
    c_step.add_argument("--exposure", type=float, default=0.0)
    c_step.add_argument("--memory-trust", type=float, default=0.0)
    c_step.add_argument("--no-fundamentals", action="store_true")
    c_step.add_argument("--json", action="store_true")

    p = tv_sub.add_parser("fundamentals", help="Fetch a fundamentals snapshot and evaluate the preset gate.")
    p.add_argument("symbol")
    p.add_argument("--preset", default="position-equity-1d-fundamental")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--json", action="store_true")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_presets(args: argparse.Namespace) -> int:
    rows = list_presets(horizon=args.horizon, market=args.market)
    if args.json:
        print(json.dumps([r.to_dict() for r in rows], indent=2))
        return 0
    print(f"{'preset':<34} {'horizon':<9} {'market':<7} {'tf':<10} {'family':<24} shorts")
    for r in rows:
        print(f"{r.name:<34} {r.horizon:<9} {r.market:<7} {r.tf.label:<10} {r.family:<24} {'yes' if r.allow_short else 'no'}")
    print(f"\n{len(rows)} presets · timeframes: {', '.join(TIMEFRAMES)}")
    return 0


def cmd_pine(args: argparse.Namespace) -> int:
    if args.all:
        out = Path(args.dir)
        out.mkdir(parents=True, exist_ok=True)
        for preset in PRESETS.values():
            src = generate_pine(preset)
            problems = lint_pine(src)
            if problems:
                print(f"{preset.name}: {problems}", file=sys.stderr)
                return 1
            (out / pine_filename(preset)).write_text(src, encoding="utf-8")
            print(f"wrote {out / pine_filename(preset)}")
        return 0
    if not args.preset:
        print("preset name required (or --all)", file=sys.stderr)
        return 2
    preset = get_preset(args.preset)
    if args.timeframe:
        preset = preset.with_timeframe(args.timeframe)
    src = generate_pine(preset)
    problems = lint_pine(src)
    if problems:
        print(f"lint: {problems}", file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).write_text(src, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(src)
    return 0


def _print_metrics(metrics: dict[str, Any]) -> None:
    order = (
        "net_profit_pct", "total_trades", "win_rate_pct", "profit_factor", "expectancy_pct", "sqn",
        "sharpe", "sortino", "max_drawdown_pct", "cagr_pct", "buy_hold_return_pct", "exposure_pct",
        "avg_bars_in_trade", "trades_per_year", "commission_paid", "years", "exit_reasons",
    )
    for k in order:
        if k in metrics:
            print(f"  {k:<22} {metrics[k]}")


def cmd_backtest(args: argparse.Namespace) -> int:
    preset = get_preset(args.preset)
    if args.timeframe:
        preset = preset.with_timeframe(args.timeframe)
    market = guess_market(args.symbol)
    if market != preset.market:
        print(f"note: {args.symbol} looks like {market} but preset is for {preset.market}; running anyway.", file=sys.stderr)
    bars, src = fetch_bars(args.symbol, preset.timeframe, source=args.source, limit=args.limit, seed=args.seed, market=market)
    res = run_backtest(bars, preset, symbol=args.symbol, cfg=EmulatorConfig())
    out: dict[str, Any] = res.to_dict(include_trades=args.trades)
    out["source"] = src
    if args.folds > 0:
        try:
            out["walk_forward"] = walk_forward(bars, preset, symbol=args.symbol, folds=args.folds).to_dict()
        except ValueError as exc:
            out["walk_forward"] = {"error": str(exc)}
    if args.monte_carlo:
        out["monte_carlo"] = monte_carlo_trades(res.trades, position_fraction=preset.risk.qty_pct_equity / 100.0)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0
    print(f"=== {preset.name} · {args.symbol} · {preset.tf.label} · source={src} · bars={len(bars)} ===")
    print(f"  range: {out['start']} → {out['end']}")
    _print_metrics(res.metrics)
    if "walk_forward" in out:
        wf = out["walk_forward"]
        print("  walk-forward (OOS):")
        for k, v in (wf.get("oos_metrics") or {}).items():
            print(f"    {k:<24} {v}")
        if wf.get("oos_is_ratio") is not None:
            print(f"    {'oos_is_ratio':<24} {wf['oos_is_ratio']}")
    if "monte_carlo" in out:
        print(f"  monte-carlo: {json.dumps(out['monte_carlo'])}")
    if args.trades:
        for t in out.get("trades", []):
            print(f"  {t['side']:<5} {t['entry_time']} {t['entry_price']:>12} → {t['exit_time']} {t['exit_price']:>12} {t['exit_reason']:<8} {t['pnl_pct']:+.3f}%")
    print("  never_live: True (simulated fills only)")
    return 0


def _runner_from_args(args: argparse.Namespace) -> DeskRunner:
    return DeskRunner(
        source=getattr(args, "source", "auto"),
        folds=getattr(args, "folds", 3),
        monte_carlo=not getattr(args, "no_monte_carlo", False),
        workers=getattr(args, "workers", 1),
        fetch_pause=getattr(args, "pause", 0.0),
        use_fundamentals=not getattr(args, "no_fundamentals", False),
    )


def cmd_desk_run(args: argparse.Namespace) -> int:
    runner = _runner_from_args(args)
    report = runner.run(
        _csv_list(args.symbols),
        presets=_csv_list(args.presets) or None,
        timeframes=_csv_list(args.timeframes) or None,
        limit=args.limit,
        seed=args.seed,
        export_pine=args.export_pine,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print("\n".join(report.summary_lines()))
    return 0


def cmd_desk_status(args: argparse.Namespace) -> int:
    memory = DeskMemory.load()
    latest = Path("data") / "tradingview" / "reports" / "latest.json"
    last: dict[str, Any] | None = None
    if latest.is_file():
        try:
            last = json.loads(latest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            last = None
    status = {
        "lead": DESK_LEAD,
        "risk": DESK_RISK,
        "review": DESK_REVIEW,
        "members": [{"name": n, "role": r} for n, r in DESK_MEMBERS],
        "presets": len(PRESETS),
        "memory": memory.to_context(),
        "last_report": {k: last.get(k) for k in ("started_at", "finished_at", "ranked", "proposals")} if last else None,
        "never_live": True,
    }
    if args.json:
        print(json.dumps(status, indent=2, default=str))
        return 0
    print("=== TradingView desk ===")
    print(f"  lead: {DESK_LEAD} · risk: {DESK_RISK} · review: {DESK_REVIEW} (critical-only)")
    for n, r in DESK_MEMBERS:
        print(f"  {n:<6} {r}")
    print(f"  presets: {len(PRESETS)} · memory synapses: {len(memory.synapses)} · consolidations: {memory.consolidations}")
    for text in memory.lessons[:6]:
        print(f"  lesson: {text}")
    if last:
        print(f"  last run: {last.get('started_at')} → {last.get('finished_at')}")
        for r in (last.get("ranked") or [])[:5]:
            print(f"    {r['reward']:+.3f} {r['preset']} {r['symbol']}@{r['timeframe']}")
    print("  never_live: True")
    return 0


def cmd_universe(args: argparse.Namespace) -> int:
    entries, meta = load_universe(
        n=args.n,
        exchanges=tuple(_csv_list(args.exchanges)) or None,
        refresh=args.refresh,
        offline=args.offline,
    )
    if args.csv:
        with Path(args.csv).open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["symbol", "name", "exchange"])
            for e in entries:
                w.writerow([e.symbol, e.name, e.exchange])
    if args.json:
        print(json.dumps({"meta": meta, "entries": [e.to_dict() for e in entries]}, indent=2))
        return 0
    print(f"=== US equity universe · source={meta.get('source')} · listed={meta.get('total_listed')} · selected={meta.get('selected')} ===")
    for exch, n in (meta.get("selected_by_exchange") or {}).items():
        print(f"  {exch:<14} {n}")
    for e in entries[:15]:
        print(f"  {e.symbol:<7} {e.exchange:<14} {e.name}")
    if len(entries) > 15:
        print(f"  … {len(entries) - 15} more")
    return 0


def cmd_universe_sweep(args: argparse.Namespace) -> int:
    entries, meta = load_universe(n=args.n, exchanges=tuple(_csv_list(args.exchanges)) or None)
    batch = entries[args.offset : args.offset + args.limit]
    runner = _runner_from_args(args)
    preset = get_preset(args.preset)
    tfs = [args.timeframe] if args.timeframe else None
    report = runner.run([e.symbol for e in batch], presets=[preset.name], timeframes=tfs, export_pine=False)
    summary = {
        "universe_source": meta.get("source"),
        "universe_selected": meta.get("selected"),
        "batch": {"offset": args.offset, "limit": args.limit, "symbols": [e.symbol for e in batch]},
        "next_offset": args.offset + args.limit if args.offset + args.limit < len(entries) else None,
        "rows": len(report.rows),
        "errors": sum(1 for r in report.rows if r.error),
        "top": report.to_dict()["ranked"][:10],
        "memory_preset_trust": report.memory.get("preset_trust"),
    }
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0
    print("\n".join(report.summary_lines()))
    print(f"  batch {args.offset}..{args.offset + len(batch)} of {len(entries)} · next --offset {summary['next_offset']}")
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    memory = DeskMemory.load()
    ctx = memory.to_context()
    ctx["best_edges"] = memory.best_edges(args.edges)
    ctx["worst_edges"] = memory.worst_edges(args.edges)
    if args.json:
        print(json.dumps(ctx, indent=2, default=str))
        return 0
    print(f"=== desk neural memory · synapses={ctx['synapses']} · episodes={ctx['episodes']} · consolidations={ctx['consolidations']} ===")
    print("  preset trust:")
    for k, v in ctx["preset_trust"].items():
        print(f"    {v:+.3f} {k}")
    print("  timeframe trust:")
    for k, v in ctx["timeframe_trust"].items():
        print(f"    {v:+.3f} {k}")
    print("  best edges:")
    for row in ctx["best_edges"]:
        print(f"    {float(row['weight']):+.3f} {row['preset']} {row['symbol']}@{row['timeframe']} (n={row['samples']})")
    print("  worst edges:")
    for row in ctx["worst_edges"]:
        print(f"    {float(row['weight']):+.3f} {row['preset']} {row['symbol']}@{row['timeframe']} (n={row['samples']})")
    for text in ctx["lessons"]:
        print(f"  lesson: {text}")
    return 0


def cmd_connectome_status(args: argparse.Namespace) -> int:
    memory = DeskMemory.load()
    brain = FlyConnectome.from_json(memory.connectome)
    ctx = brain.to_context()
    if args.json:
        print(json.dumps(ctx, indent=2))
        return 0
    print("=== fly connectome → motor mapping ===")
    for region, info in REGIONS.items():
        print(f"  {region:<19} {info['biology']:<42} → {info['role']}")
    print(f"  DN channels: {', '.join(DN_CHANNELS)}")
    print(f"  KCs: {ctx['n_kc']} (k={ctx['k_active']}) · steps: {ctx['steps']} · mean valence: {ctx['mean_valence_weight']:+.3f}")
    print(f"  recent dopamine: {ctx['recent_dopamine']}")
    print("  human_final_say: True (proposals only — never orders)")
    return 0


def cmd_connectome_step(args: argparse.Namespace) -> int:
    memory = DeskMemory.load()
    brain = FlyConnectome.from_json(memory.connectome)
    sense = MarketSense(
        symbol=args.symbol,
        trend=args.trend,
        momentum=args.momentum,
        orderflow=args.orderflow,
        volatility=args.volatility,
        drawdown=args.drawdown,
        memory_trust=args.memory_trust,
        exposure=args.exposure,
        fundamentals_ok=not args.no_fundamentals,
    )
    cmd = brain.step(sense)
    if args.json:
        print(json.dumps(cmd.to_dict(), indent=2))
        return 0
    print(f"=== motor proposal for {args.symbol} (requires human approval) ===")
    print(f"  action: {cmd.action} · size: {cmd.size_pct}% · confidence: {cmd.confidence:.2f}")
    print(f"  steering error: {cmd.steering_error:+.3f} · valence: {cmd.valence:+.3f} · inhibition: {cmd.inhibition:.2f}")
    for k, v in cmd.channel_drive.items():
        print(f"    DN {k:<12} {v:.3f}")
    print(f"  {cmd.note}")
    return 0


def cmd_fundamentals(args: argparse.Namespace) -> int:
    preset = get_preset(args.preset)
    feed = YahooFundamentals()
    snap = feed.get(args.symbol, refresh=args.refresh)
    ok, reasons = gate_passes(snap, preset.fundamentals)
    out = {"symbol": args.symbol, "snapshot": snap.to_dict() if snap else None, "gate": preset.fundamentals.__dict__, "passes": ok, "reasons": reasons}
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"=== fundamentals · {args.symbol} · gate from {preset.name} ===")
    if snap:
        for k, v in snap.to_dict().items():
            print(f"  {k:<22} {v}")
    else:
        print("  snapshot unavailable")
    print(f"  passes: {ok} {('— ' + '; '.join(reasons)) if reasons else ''}")
    return 0


def dispatch_tradingview(args: argparse.Namespace) -> int:
    cmd = args.tradingview_command
    if cmd == "presets":
        return cmd_presets(args)
    if cmd == "pine":
        return cmd_pine(args)
    if cmd == "backtest":
        return cmd_backtest(args)
    if cmd == "desk":
        if args.desk_command == "run":
            return cmd_desk_run(args)
        if args.desk_command == "status":
            return cmd_desk_status(args)
        return 2
    if cmd == "universe":
        return cmd_universe(args)
    if cmd == "universe-sweep":
        return cmd_universe_sweep(args)
    if cmd == "memory":
        return cmd_memory(args)
    if cmd == "connectome":
        if args.connectome_command == "status":
            return cmd_connectome_status(args)
        if args.connectome_command == "step":
            return cmd_connectome_step(args)
        return 2
    if cmd == "fundamentals":
        return cmd_fundamentals(args)
    return 2
