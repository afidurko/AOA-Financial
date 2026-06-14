"""Command-line interface for the AOA Financial swarm.

Commands:
  aoa doctor     Validate configuration & connectivity.
  aoa status     Show account, positions, and market clock.
  aoa run        Run a single analysis→decision→execution cycle.
  aoa loop       Run cycles continuously on the configured cadence.
  aoa journal    Print the tail of the decision/trade journal.
  aoa analyze    Analyze the historical trend of a symbol.
  aoa simulate   Monte-Carlo + scenario stress-test a symbol's forward path.
  aoa scenarios  List the built-in stress-scenario library.
"""

from __future__ import annotations

import argparse
import sys
import time

from aoa.brokerage.alpaca import AlpacaBroker
from aoa.brokerage.base import Broker, BrokerError
from aoa.config import Config
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient, LLMError
from aoa.simulation.scenarios import extract_scenario, list_scenarios
from aoa.simulation.simulator import MarketSimulator, SimulationConfig
from aoa.simulation.trends import analyze_trends
from aoa.swarm.orchestrator import CycleResult, Orchestrator


def build_broker(cfg: Config) -> Broker:
    return AlpacaBroker(cfg.alpaca_key_id, cfg.alpaca_secret_key, live=cfg.alpaca_live)


def build_llm(cfg: Config) -> LLMClient:
    return LLMClient(cfg.anthropic_api_key, model=cfg.model, effort=cfg.effort)


def build_orchestrator(cfg: Config) -> Orchestrator:
    return Orchestrator(cfg, build_broker(cfg), build_llm(cfg), Journal())


# --------------------------------------------------------------------- output
def _print_cycle(result: CycleResult) -> None:
    bb = result.blackboard
    print("\n=== Cycle summary ===")
    if bb.account:
        print(
            f"Equity ${bb.account.equity:,.2f} | settled cash "
            f"${bb.account.settled_cash:,.2f} | positions {len(bb.positions)}"
        )
    print(f"Universe: {len(bb.universe)} symbols | candidates: {len(bb.candidates)}")
    for cand in bb.candidates:
        print(f"  • {cand.get('symbol'):<6} p={cand.get('priority'):.2f}  {cand.get('reason')}")
    if bb.commentary:
        print(f"\nPM commentary: {bb.commentary}")
    if bb.proposals:
        print("\nProposals:")
        for p in bb.proposals:
            flag = "APPROVED" if p.approved else "blocked "
            print(
                f"  [{flag}] {p.side.value.upper():<4} {p.qty} {p.symbol} "
                f"({p.strategy}, ~${p.est_notional:,.0f})  {'; '.join(p.risk_notes)}"
            )
    else:
        print("\nNo proposals this cycle.")
    if result.execution:
        rep = result.execution
        tag = "DRY-RUN (nothing submitted)" if rep.dry_run else "EXECUTED"
        print(
            f"\n{tag}: submitted={len(rep.submitted)} "
            f"skipped={len(rep.skipped)} errors={len(rep.errors)}"
        )
        for err in rep.errors:
            print(f"  ! {err['symbol']}: {err['error']}")
    for note in result.notes:
        print(f"Note: {note}")


# --------------------------------------------------------------------- commands
def cmd_doctor(cfg: Config) -> int:
    print(f"AOA Financial — trading mode: {cfg.trading_mode.upper()}")
    problems = cfg.validate()
    if problems:
        print("Configuration problems:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("  ✓ Configuration looks complete.")
    try:
        broker = build_broker(cfg)
        acct = broker.get_account()
        print(f"  ✓ Broker reachable ({broker.name}); equity ${acct.equity:,.2f}.")
        print(f"  ✓ Market open: {broker.is_market_open()}")
    except BrokerError as exc:
        print(f"  ✗ Broker check failed: {exc}")
        return 1
    try:
        build_llm(cfg)
        print("  ✓ LLM client initialized.")
    except LLMError as exc:
        print(f"  ✗ LLM init failed: {exc}")
        return 1
    return 0


def cmd_status(cfg: Config) -> int:
    broker = build_broker(cfg)
    acct = broker.get_account()
    print(f"Mode: {cfg.trading_mode} | Broker: {broker.name}")
    print(
        f"Equity ${acct.equity:,.2f} | cash ${acct.cash:,.2f} | "
        f"settled ${acct.settled_cash:,.2f} | options L{acct.options_level}"
    )
    print(f"Market open: {broker.is_market_open()}")
    positions = broker.get_positions()
    if not positions:
        print("No open positions.")
        return 0
    print("\nPositions:")
    for p in positions:
        print(
            f"  {p.symbol:<22} {p.asset_class.value:<7} qty {p.qty:>8.2f} "
            f"mv ${p.market_value:>12,.2f}  uPL ${p.unrealized_pl:>+10,.2f}"
        )
    return 0


def cmd_run(cfg: Config) -> int:
    orch = build_orchestrator(cfg)
    if not orch.broker.is_market_open():
        print("Market is closed. Running analysis anyway (orders may queue/reject).")
    result = orch.run_cycle()
    _print_cycle(result)
    return 0


def cmd_loop(cfg: Config) -> int:
    orch = build_orchestrator(cfg)
    print(
        f"Starting continuous loop: mode={cfg.trading_mode}, "
        f"cadence={cfg.cycle_seconds}s. Ctrl-C to stop."
    )
    try:
        while True:
            if orch.broker.is_market_open():
                result = orch.run_cycle()
                _print_cycle(result)
            else:
                print("Market closed — sleeping.")
            time.sleep(cfg.cycle_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_analyze(cfg: Config, symbol: str, timeframe: str, limit: int) -> int:
    broker = build_broker(cfg)
    bars = broker.get_bars(symbol, timeframe, limit)
    analysis = analyze_trends(bars, symbol)
    if analysis is None:
        print(f"Not enough history for {symbol.upper()} ({len(bars)} bars).")
        return 1
    a = analysis
    print(f"=== Trend analysis: {a.symbol} ({a.n_bars} {timeframe} bars) ===")
    print(
        f"Price ${a.start_price:,.2f} → ${a.end_price:,.2f}  "
        f"({a.total_return_pct:+.2f}% total, {a.cagr_pct:+.2f}% CAGR)"
    )
    print(
        f"Trend: {a.trend.upper()} (slope {a.slope_pct_per_bar:+.3f}%/bar, "
        f"R²={a.r_squared})  |  Regime: {a.regime}"
    )
    r = a.returns
    print(
        f"Daily return: mean {r.mean_daily_pct:+.3f}%  vol {r.std_daily_pct:.3f}%  "
        f"(ann. {r.annualized_vol_pct:.1f}%)  skew {r.skew:+.2f}  kurt {r.excess_kurtosis:+.2f}"
    )
    print(
        f"Best/worst day: {r.best_day_pct:+.2f}% / {r.worst_day_pct:+.2f}%  "
        f"up-days {r.positive_day_ratio:.0%}"
    )
    print(
        f"Drawdown: max {a.max_drawdown_pct:.2f}%  current {a.current_drawdown_pct:.2f}%"
    )
    if a.drawdowns:
        print("\nNotable drawdowns (≥10%), deepest first:")
        for d in a.drawdowns[:5]:
            tag = "recovered" if d.recovered else "ongoing"
            print(
                f"  {d.depth_pct:>7.2f}%  bars {d.peak_index}→{d.trough_index} "
                f"({d.length_bars} long, {tag})"
            )
    return 0


def cmd_simulate(
    cfg: Config, symbol: str, method: str, paths: int, horizon: int, seed: int | None
) -> int:
    broker = build_broker(cfg)
    bars = broker.get_bars(symbol, "1Day", 252)
    sim = MarketSimulator(seed=seed)
    cfg_sim = SimulationConfig(
        method=method, horizon=horizon, n_paths=paths, seed=seed
    )
    result = sim.simulate(bars, cfg_sim, symbol=symbol)
    if result is None:
        print(f"Not enough history to simulate {symbol.upper()}.")
        return 1
    print(f"=== Monte-Carlo simulation: {result.symbol} ===")
    print(result.summary())

    # Stress-test the same starting price against the historical scenario library.
    stresses = sim.stress_test(result.start_price, list_scenarios())
    print(f"\n=== Scenario stress test (from ${result.start_price:,.2f}) ===")
    print(f"  {'scenario':<22}{'days':>5}{'return':>10}{'maxDD':>9}{'ending':>12}")
    for s in sorted(stresses, key=lambda x: x.total_return_pct):
        print(
            f"  {s.scenario:<22}{s.horizon_days:>5}{s.total_return_pct:>9.1f}%"
            f"{s.max_drawdown_pct:>8.1f}%{s.ending_price:>12,.2f}"
        )

    # Also replay the symbol's own most-recent window as a scenario.
    own = extract_scenario(bars, f"{symbol.upper()}_recent_{horizon}d", start=-horizon - 1)
    if own is not None:
        replay = sim.replay_scenario(result.start_price, own)
        print(
            f"\nReplay of {symbol.upper()}'s own last {own.horizon_days} bars "
            f"from current price → ${replay[-1]:,.2f} ({own.total_return_pct:+.1f}%)"
        )
    return 0


def cmd_scenarios(cfg: Config) -> int:
    print("Built-in stress scenarios:\n")
    print(f"  {'name':<22}{'days':>5}{'return':>10}{'maxDD':>9}  description")
    for s in list_scenarios():
        print(
            f"  {s.name:<22}{s.horizon_days:>5}{s.total_return_pct:>9.1f}%"
            f"{s.max_drawdown_pct:>8.1f}%  {s.description}"
        )
    return 0


def cmd_journal(cfg: Config, n: int) -> int:
    entries = Journal().tail(n)
    if not entries:
        print("Journal is empty.")
        return 0
    for e in entries:
        print(f"{e.get('ts', '')}  {e.get('event', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aoa", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Validate configuration & connectivity.")
    sub.add_parser("status", help="Show account, positions, and market clock.")
    sub.add_parser("run", help="Run a single swarm cycle.")
    sub.add_parser("loop", help="Run cycles continuously.")
    jp = sub.add_parser("journal", help="Tail the decision/trade journal.")
    jp.add_argument("-n", type=int, default=20, help="Number of entries to show.")

    ap = sub.add_parser("analyze", help="Analyze the historical trend of a symbol.")
    ap.add_argument("symbol", help="Ticker to analyze, e.g. AAPL.")
    ap.add_argument("--timeframe", default="1Day", help="Bar timeframe (default 1Day).")
    ap.add_argument("--limit", type=int, default=252, help="Number of bars (default 252).")

    sp = sub.add_parser("simulate", help="Monte-Carlo + scenario stress-test a symbol.")
    sp.add_argument("symbol", help="Ticker to simulate, e.g. AAPL.")
    sp.add_argument(
        "--method", choices=["gbm", "bootstrap"], default="gbm", help="Simulation engine."
    )
    sp.add_argument("--paths", type=int, default=1000, help="Number of Monte-Carlo paths.")
    sp.add_argument("--horizon", type=int, default=21, help="Bars to project forward.")
    sp.add_argument("--seed", type=int, default=None, help="Random seed (reproducibility).")

    sub.add_parser("scenarios", help="List the built-in stress-scenario library.")

    args = parser.parse_args(argv)
    cfg = Config.from_env()

    try:
        if args.command == "doctor":
            return cmd_doctor(cfg)
        if args.command == "status":
            return cmd_status(cfg)
        if args.command == "run":
            return cmd_run(cfg)
        if args.command == "loop":
            return cmd_loop(cfg)
        if args.command == "journal":
            return cmd_journal(cfg, args.n)
        if args.command == "analyze":
            return cmd_analyze(cfg, args.symbol, args.timeframe, args.limit)
        if args.command == "simulate":
            return cmd_simulate(
                cfg, args.symbol, args.method, args.paths, args.horizon, args.seed
            )
        if args.command == "scenarios":
            return cmd_scenarios(cfg)
    except (BrokerError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
