"""Command-line interface for the AOA Financial swarm.

Commands:
  aoa doctor     Validate configuration & connectivity.
  aoa status     Show account, positions, and market clock.
  aoa run        Run a single analysis→decision→execution cycle.
  aoa loop       Run cycles continuously on the configured cadence.
  aoa serve      Start the web dashboard and REST API.
  aoa journal    Print the tail of the decision/trade journal.
  aoa report     Summarize activity (from the journal) and live P&L.
  aoa analyze    Analyze the historical trend of a symbol.
  aoa simulate   Monte-Carlo + scenario stress-test a symbol's forward path.
  aoa scenarios  List the built-in stress-scenario library.
  aoa watch      Live-track symbols: re-analyze & re-simulate as the market moves.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from aoa.adapt.signal_adapter import SignalAdapter
from aoa.brokerage.alpaca import AlpacaBroker
from aoa.brokerage.base import Broker, BrokerError
from aoa.config import Config
from aoa.data.news import AlpacaNewsFeed, NewsFeed, NullNewsFeed
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient, LLMError
from aoa.reporting import position_pnl, summarize_journal
from aoa.simulation.live import LiveMarketTracker
from aoa.simulation.scenarios import extract_scenario, list_scenarios
from aoa.simulation.simulator import MarketSimulator, SimulationConfig
from aoa.simulation.trends import analyze_trends
from aoa.state import StateStore
from aoa.swarm.orchestrator import CycleResult, Orchestrator
from aoa.team.orchestrator import TeamCycleResult, TeamOrchestrator


def build_broker(cfg: Config) -> Broker:
    return AlpacaBroker(
        cfg.alpaca_key_id,
        cfg.alpaca_secret_key,
        live=cfg.alpaca_live,
        bar_feed=cfg.bar_feed,
        data_feed=cfg.alpaca_data_feed,
        bar_adjustment=cfg.alpaca_bar_adjustment,
    )


def build_llm(cfg: Config) -> LLMClient:
    return LLMClient(cfg.anthropic_api_key, model=cfg.model, effort=cfg.effort)


def build_news(cfg: Config) -> NewsFeed:
    if not cfg.news_enabled or not cfg.has_brokerage_creds:
        return NullNewsFeed()
    return AlpacaNewsFeed(
        cfg.alpaca_key_id,
        cfg.alpaca_secret_key,
        lookback_hours=cfg.news_lookback_hours,
    )


def build_signal_adapter(cfg: Config) -> SignalAdapter | None:
    if not cfg.adapt_enabled:
        return None
    return SignalAdapter.load_or_new(
        cfg.adapt_path,
        rank=cfg.adapt_rank,
        alpha=cfg.adapt_alpha,
        lr=cfg.adapt_lr,
    )


def save_signal_adapter(cfg: Config, adapter: SignalAdapter | None) -> None:
    if adapter is None:
        return
    path = Path(cfg.adapt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    adapter.save(path)


def build_orchestrator(cfg: Config) -> Orchestrator:
    return Orchestrator(
        cfg,
        build_broker(cfg),
        build_llm(cfg),
        Journal(cfg.journal_path),
        build_news(cfg),
        signal_adapter=build_signal_adapter(cfg),
    )


def _print_environment(cfg: Config) -> None:
    profile = cfg.profile or cfg.env
    print(
        f"Environment: {cfg.env} | profile: {profile} | "
        f"mode: {cfg.trading_mode} | data: {cfg.data_dir}"
    )
    print(f"Journal: {cfg.journal_path}")


def build_team(cfg: Config) -> TeamOrchestrator:
    return TeamOrchestrator(
        cfg,
        build_broker(cfg),
        build_llm(cfg),
        Journal(cfg.journal_path),
        build_news(cfg),
        signal_adapter=build_signal_adapter(cfg),
    )


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


def _print_team(result: TeamCycleResult) -> None:
    if result.health:
        print("\n=== Bob — systems health ===")
        print(f"  {result.health.summary}")
        for check in result.health.checks:
            print(f"  [{check.status.value.upper():<8}] {check.name}: {check.detail}")
    if result.trends:
        print("\n=== Tom — trend analysis ===")
        for t in result.trends:
            print(
                f"  {t.symbol:<6} {t.direction.value:<8} strength={t.strength:.2f}  {t.rationale[:60]}"
            )
    if result.algorithms:
        print("\n=== Julie — algorithm validation ===")
        for a in result.algorithms:
            flag = "validated" if a.validated else "unvalidated"
            print(f"  {a.symbol:<6} [{flag}] strength={a.adjusted_strength:.2f}  {a.method_notes[:50]}")
    if result.decision:
        print("\n=== Alan — decision brief ===")
        print(f"  {result.decision.summary} (confidence={result.decision.confidence:.2f})")
        for rec in result.decision.recommendations:
            print(
                f"  • {rec.get('symbol', '?'):<6} {rec.get('action', '?'):<18} "
                f"conv={rec.get('conviction', 0):.2f}  {rec.get('rationale', '')[:50]}"
            )
    if result.remediation and result.remediation.actions:
        print("\n=== Aaron — fixes applied ===")
        for fix in result.remediation.actions:
            flag = "fixed" if fix.success else "failed"
            print(f"  [{flag}] {fix.target}: {fix.action} — {fix.detail}")
    if result.ceo:
        print("\n=== Aaron — CEO review ===")
        print(f"  {result.ceo.summary}")
        for m in result.ceo.team_status:
            flag = "✓" if m.completed else "✗"
            print(f"  {flag} {m.name} ({m.role}): {m.notes or 'ok'}")
        if result.ceo.fixes_applied:
            print("\n  Fixes applied this cycle:")
            for fix in result.ceo.fixes_applied:
                print(f"    • {fix.get('target')}: {fix.get('detail')}")
        if result.ceo.user_notifications:
            print("\n  ⚠ Escalated to your iPhone:")
            for n in result.ceo.user_notifications:
                print(f"    • {n}")
        if result.ceo.iphone_notifications_sent:
            print("\n  📱 iPhone delivery log:")
            for n in result.ceo.iphone_notifications_sent:
                print(f"    • {n}")
    if result.halted:
        print(f"\nCycle halted: {result.halt_reason}")
    elif result.cycle:
        _print_cycle(result.cycle)


# --------------------------------------------------------------------- commands
def cmd_doctor(cfg: Config, *, offline: bool = False) -> int:
    _print_environment(cfg)
    problems = cfg.validate()
    if problems:
        print("Configuration problems:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    tf_keys = ", ".join(t.key for t in cfg.bar_timeframes)
    print("  ✓ Configuration looks complete.")
    print(f"  ✓ Bar timeframes: {tf_keys}")
    print(f"  ✓ Bar feed: {cfg.bar_feed} | news limit: {cfg.news_limit}")
    if cfg.is_test:
        print("  ✓ Test environment — skipping broker/LLM connectivity checks.")
        return 0
    if offline:
        print("  ✓ Offline mode — skipped broker and LLM connectivity checks.")
        return 0
    try:
        broker = build_broker(cfg)
        acct = broker.get_account()
        print(f"  ✓ Broker reachable ({broker.name}); equity ${acct.equity:,.2f}.")
        latest = broker.verify_stock_bars("SPY", limit=1)
        feed = cfg.alpaca_data_feed or "default"
        print(
            f"  ✓ Live bars API; SPY last close ${latest.close:,.2f} "
            f"({latest.timestamp.date()}, feed={feed}, "
            f"adjustment={cfg.alpaca_bar_adjustment})."
        )
    except BrokerError as exc:
        print(f"  ✗ Broker check failed: {exc}")
        return 1
    try:
        llm = build_llm(cfg)
        print("  ✓ LLM client initialized.")
        llm.ping()
        print(f"  ✓ LLM reachable (model={cfg.model}).")
    except LLMError as exc:
        print(f"  ✗ LLM check failed: {exc}")
        return 1
    if cfg.adapt_enabled:
        adapter = build_signal_adapter(cfg)
        print(
            f"  ✓ Low-rank signal adaptation ON "
            f"(rank={cfg.adapt_rank}, alpha={cfg.adapt_alpha}, "
            f"updates so far={adapter.updates if adapter else 0}, path={cfg.adapt_path})"
        )
    else:
        print("  · Low-rank signal adaptation OFF (set AOA_ADAPT_ENABLED=true to enable).")
    return 0


def cmd_status(cfg: Config) -> int:
    _print_environment(cfg)
    broker = build_broker(cfg)
    acct = broker.get_account()
    state = StateStore(cfg.state_path)
    unsettled = state.unsettled_cash()
    effective = max(0.0, acct.settled_cash - unsettled)
    print(f"Mode: {cfg.trading_mode} | Broker: {broker.name}")
    print(
        f"Equity ${acct.equity:,.2f} | cash ${acct.cash:,.2f} | "
        f"settled ${acct.settled_cash:,.2f} | options L{acct.options_level}"
    )
    print(
        f"Unsettled (tracked) ${unsettled:,.2f} | "
        f"effective available ${effective:,.2f}"
    )
    baseline = state.starting_equity_for_today(acct.equity)
    daily_pl = acct.equity - baseline
    print(f"Day baseline ${baseline:,.2f} | day P/L ${daily_pl:+,.2f}")
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


def _cycle_exit_code(result: CycleResult) -> int:
    if result.execution and result.execution.errors:
        return 1
    return 0


def cmd_run(cfg: Config) -> int:
    team = build_team(cfg)
    _print_environment(cfg)
    if not team.broker.is_market_open():
        print("Market is closed. Running analysis anyway (orders may queue/reject).")
    result = team.run_cycle()
    _print_team(result)
    save_signal_adapter(cfg, team.trading.signal_adapter)
    if result.halted:
        return 1
    if result.cycle:
        return _cycle_exit_code(result.cycle)
    return 0


def cmd_loop(cfg: Config) -> int:
    team = build_team(cfg)
    _print_environment(cfg)
    print(
        f"Starting continuous loop (team mode): mode={cfg.trading_mode}, "
        f"cadence={cfg.cycle_seconds}s. Ctrl-C to stop."
    )
    try:
        while True:
            if team.broker.is_market_open():
                result = team.run_cycle()
                _print_team(result)
                save_signal_adapter(cfg, team.trading.signal_adapter)
                if result.halted:
                    print(f"Cycle halted: {result.halt_reason}", file=sys.stderr)
                elif result.cycle and _cycle_exit_code(result.cycle):
                    print("Cycle finished with execution errors.", file=sys.stderr)
            else:
                print("Market closed — sleeping.")
            time.sleep(cfg.cycle_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_team_health(cfg: Config) -> int:
    team = build_team(cfg)
    health = team.run_health_check()
    _print_team(TeamCycleResult(health=health))
    return 0 if health.can_proceed else 1


def cmd_team_brief(cfg: Config) -> int:
    team = build_team(cfg)
    health = team.run_health_check()
    remediation = team.aaron.attempt_health_recovery(
        health,
        market_cache_clear=team.trading.market.clear_cache,
    )
    if remediation.health:
        health = remediation.health
    if not health.can_proceed:
        ceo = team.aaron.review(
            health=health,
            tom_done=False,
            julie_done=False,
            alan_done=False,
            decision=None,
            halted=True,
            halt_reason=health.summary,
            remediation=remediation,
        )
        _print_team(
            TeamCycleResult(
                health=health,
                ceo=ceo,
                remediation=remediation,
                halted=True,
                halt_reason=health.summary,
            )
        )
        return 1
    trends, algorithms, decision = team.run_team_brief()
    ceo = team.aaron.review(
        health=health,
        tom_done=bool(trends),
        julie_done=bool(algorithms),
        alan_done=True,
        decision=decision,
        tom_count=len(trends),
        julie_count=len(algorithms),
        remediation=remediation,
    )
    _print_team(
        TeamCycleResult(
            health=health,
            trends=trends,
            algorithms=algorithms,
            decision=decision,
            ceo=ceo,
            remediation=remediation,
        )
    )
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
    print("Built-in stress scenarios ([real] = actual historical daily returns):\n")
    print(f"  {'name':<26}{'kind':>7}{'days':>5}{'return':>10}{'maxDD':>9}  description")
    for s in sorted(list_scenarios(), key=lambda x: ("actual" in x.tags, x.name)):
        kind = "[real]" if "actual" in s.tags else "[synth]"
        print(
            f"  {s.name:<26}{kind:>7}{s.horizon_days:>5}{s.total_return_pct:>9.1f}%"
            f"{s.max_drawdown_pct:>8.1f}%  {s.description}"
        )
    return 0


def cmd_watch(
    cfg: Config,
    symbols: list[str],
    interval: float,
    iterations: int | None,
    horizon: int,
    paths: int,
    halflife: int,
) -> int:
    broker = build_broker(cfg)
    tracker = LiveMarketTracker(
        broker,
        sim_config=SimulationConfig(horizon=horizon, n_paths=paths),
        ewma_halflife=halflife,
        journal=Journal(),
    )
    syms = [s.upper() for s in symbols]
    mode = "continuously" if iterations is None else f"{iterations}×"
    print(
        f"Live-tracking {', '.join(syms)} every {interval:g}s ({mode}); "
        f"adaptive half-life {halflife} bars. Ctrl-C to stop."
    )

    def _print(update) -> None:
        stamp = update.timestamp.strftime("%H:%M:%S")
        print(f"[{stamp}] {update.summary()}")

    try:
        tracker.stream(
            syms,
            interval=interval,
            iterations=iterations,
            on_update=_print,
            market_gate=broker.is_market_open,
        )
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_journal(cfg: Config, n: int) -> int:
    entries = Journal(cfg.journal_path).tail(n)
    if not entries:
        print("Journal is empty.")
        return 0
    for e in entries:
        print(f"{e.get('ts', '')}  {e.get('event', '')}")
    return 0


def cmd_serve(cfg: Config) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "Web server requires optional dependencies. Install with: pip install -e \".[web]\"",
            file=sys.stderr,
        )
        return 1
    from aoa.web.app import create_app

    app = create_app(cfg)
    print(
        f"AOA dashboard at http://{cfg.web_host}:{cfg.web_port}/ "
        f"(API docs at /api/docs)"
    )
    uvicorn.run(app, host=cfg.web_host, port=cfg.web_port, log_level="info")
    return 0


def cmd_report(cfg: Config) -> int:
    summary = summarize_journal(Journal(cfg.journal_path).read_all())
    print("=== Activity (from journal) ===")
    if summary.cycles == 0:
        print("No cycles recorded yet.")
    else:
        print(f"Cycles: {summary.cycles}  ({summary.first_ts} → {summary.last_ts})")
        print(f"Candidates analyzed: {summary.candidates_total}")
        print(
            f"Orders submitted: {summary.orders_submitted} "
            f"{summary.orders_by_side or ''} | dry-run: {summary.dry_runs} | "
            f"errors: {summary.errors} | re-entry skips: {summary.reentry_skips}"
        )
        if summary.blocked:
            print(f"Risk-blocked proposals: {len(summary.blocked)}")
            for reason, count in sorted(
                summary.blocked_reason_counts.items(), key=lambda kv: -kv[1]
            )[:5]:
                print(f"  {count:>3}× {reason}")

    # Live P&L snapshot (best effort — needs broker connectivity).
    print("\n=== Live P&L snapshot ===")
    try:
        broker = build_broker(cfg)
        acct = broker.get_account()
        positions = broker.get_positions()
        state = StateStore(cfg.state_path)
        baseline = state.starting_equity_for_today(acct.equity)
        unsettled = state.unsettled_cash()
        pnl = position_pnl(positions)
        print(
            f"Equity ${acct.equity:,.2f} | day baseline ${baseline:,.2f} | "
            f"day P/L ${acct.equity - baseline:+,.2f}"
        )
        print(
            f"Open positions: {pnl.n} | unrealized P/L ${pnl.unrealized_pl:+,.2f} "
            f"({pnl.winners} up / {pnl.losers} down)"
        )
        if pnl.best:
            print(f"  best:  {pnl.best[0]} ${pnl.best[1]:+,.2f}")
        if pnl.worst:
            print(f"  worst: {pnl.worst[0]} ${pnl.worst[1]:+,.2f}")
        if unsettled:
            print(f"Unsettled proceeds: ${unsettled:,.2f}")
    except BrokerError as exc:
        print(f"(live snapshot unavailable: {exc})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aoa", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Validate configuration & connectivity.")
    doctor.add_argument(
        "--offline",
        action="store_true",
        help="Validate config only; skip live broker and LLM checks.",
    )
    sub.add_parser("status", help="Show account, positions, and market clock.")
    sub.add_parser("run", help="Run a single team-coordinated swarm cycle.")
    sub.add_parser("loop", help="Run team cycles continuously.")
    team = sub.add_parser("team", help="Team-specific commands.")
    team_sub = team.add_subparsers(dest="team_command", required=True)
    team_sub.add_parser("health", help="Run Bob's systems health check.")
    team_sub.add_parser("brief", help="Run Tom→Julie→Alan analysis without trading.")
    sub.add_parser("serve", help="Start the web dashboard and REST API.")
    jp = sub.add_parser("journal", help="Tail the decision/trade journal.")
    jp.add_argument("-n", type=int, default=20, help="Number of entries to show.")
    sub.add_parser("report", help="Summarize activity and live P&L.")

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

    wp = sub.add_parser("watch", help="Live-track symbols: re-analyze & re-simulate.")
    wp.add_argument("symbols", nargs="+", help="One or more tickers, e.g. AAPL MSFT.")
    wp.add_argument("--interval", type=float, default=60.0, help="Seconds between refreshes.")
    wp.add_argument(
        "--iterations", type=int, default=None, help="Stop after N refreshes (default: forever)."
    )
    wp.add_argument("--horizon", type=int, default=21, help="Bars to project forward.")
    wp.add_argument("--paths", type=int, default=500, help="Monte-Carlo paths per refresh.")
    wp.add_argument(
        "--halflife", type=int, default=63, help="Recency half-life (bars) for adaptation."
    )

    args = parser.parse_args(argv)
    cfg = Config.from_env()

    try:
        if args.command == "doctor":
            return cmd_doctor(cfg, offline=getattr(args, "offline", False))
        if args.command == "status":
            return cmd_status(cfg)
        if args.command == "run":
            return cmd_run(cfg)
        if args.command == "loop":
            return cmd_loop(cfg)
        if args.command == "team":
            if args.team_command == "health":
                return cmd_team_health(cfg)
            if args.team_command == "brief":
                return cmd_team_brief(cfg)
        if args.command == "serve":
            return cmd_serve(cfg)
        if args.command == "journal":
            return cmd_journal(cfg, args.n)
        if args.command == "report":
            return cmd_report(cfg)
        if args.command == "analyze":
            return cmd_analyze(cfg, args.symbol, args.timeframe, args.limit)
        if args.command == "simulate":
            return cmd_simulate(
                cfg, args.symbol, args.method, args.paths, args.horizon, args.seed
            )
        if args.command == "scenarios":
            return cmd_scenarios(cfg)
        if args.command == "watch":
            return cmd_watch(
                cfg,
                args.symbols,
                args.interval,
                args.iterations,
                args.horizon,
                args.paths,
                args.halflife,
            )
    except (BrokerError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
