"""Command-line interface for the AOA Financial swarm.

Commands:
  aoa bars       Fetch recent stock and/or crypto OHLCV bars from Alpaca.
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
  aoa workloop   Run the autonomous discover→merge improvement loop.
  aoa repair     Fable 5 repair loop — discover issues and queue fixes.
  aoa burnin     Run N paper cycles and print a burn-in summary.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from aoa.adapt.signal_adapter import SignalAdapter
from aoa.brokerage.alpaca import AlpacaBroker
from aoa.brokerage.alpaca_bars import (
    AlpacaBarsFetcher,
    bars_config_from_env,
    partition_symbols,
)
from aoa.brokerage.base import Broker, BrokerError
from aoa.config import Config
from aoa.data.news import AlpacaNewsFeed, NewsFeed, NullNewsFeed
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient, LLMError
from aoa.repair.orchestrator import RepairOrchestrator
from aoa.reporting import position_pnl, summarize_journal
from aoa.simulation.live import LiveMarketTracker
from aoa.simulation.scenarios import extract_scenario, list_scenarios
from aoa.simulation.simulator import MarketSimulator, SimulationConfig
from aoa.simulation.trends import analyze_trends
from aoa.state import StateStore
from aoa.swarm.orchestrator import CycleResult, Orchestrator
from aoa.team.orchestrator import TeamCycleResult, TeamOrchestrator
from aoa.workloop.models import STAGE_ORDER
from aoa.workloop.orchestrator import WorkloopOrchestrator
from aoa.workloop.scheduler import build_scheduler


def build_broker(cfg: Config) -> Broker:
    return AlpacaBroker(
        cfg.alpaca_key_id,
        cfg.alpaca_secret_key,
        oauth_token=cfg.alpaca_oauth_token,
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
        oauth_token=cfg.alpaca_oauth_token,
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
        print("\n=== Bob — systems health & code integrity ===")
        print(f"  {result.health.summary}")
        for check in result.health.checks:
            print(f"  [{check.status.value.upper():<8}] {check.name}: {check.detail}")
    if result.trends:
        print("\n=== Tom — trend analysis ===")
        for t in result.trends:
            print(
                f"  {t.symbol:<6} {t.direction.value:<8} strength={t.strength:.2f}  "
                f"{t.rationale[:60]}"
            )
    if result.algorithms:
        print("\n=== Julie — algorithm & code clarity ===")
        for a in result.algorithms:
            flag = "validated" if a.validated else "unvalidated"
            print(
                f"  {a.symbol:<6} [{flag}] strength={a.adjusted_strength:.2f}  "
                f"{a.method_notes[:50]}"
            )
    if result.market_contexts:
        print("\n=== Morgan — market, equity & options volume ===")
        for m in result.market_contexts:
            print(
                f"  {m.symbol:<6} {m.volume_regime:<8} ratio={m.volume_ratio}  "
                f"{m.summary[:50]}"
            )
            if m.options_volume_note:
                print(f"         options: {m.options_volume_note[:70]}")
    if result.catalysts:
        print("\n=== Hailey — news & catalysts ===")
        for c in result.catalysts:
            print(
                f"  {c.symbol:<6} risk={c.event_risk:<6} sentiment={c.headline_sentiment:<8}  "
                f"{c.catalyst_summary[:50]}"
            )
    if result.risk_plans:
        print("\n=== Andrea — pre-execution risk plans ===")
        for r in result.risk_plans:
            p = r.plan
            flag = "OK" if r.approved_for_execution else "HOLD"
            print(
                f"  [{flag}] {r.symbol:<6} qty={p.quantity:.0f} cost=${p.est_cost:,.0f}  "
                f"entry={p.entry_price} stop={p.stop_loss} tp={p.take_profit}  "
                f"R:R={p.reward_risk_ratio}"
            )
            if r.hedging:
                print(f"         hedge: {r.hedging[:60]}")
    if result.assistant:
        print("\n=== Alex — your priorities ===")
        print(f"  Focus: {result.assistant.focus}")
        print(f"  {result.assistant.summary}")
        for label, items in (
            ("MUST DO", result.assistant.must_do),
            ("SHOULD DO", result.assistant.should_do),
            ("CAN WAIT", result.assistant.can_wait),
        ):
            if items:
                print(f"\n  {label}:")
                for item in items:
                    print(f"    • {item.title}: {item.detail[:60]}")
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
def _cycle_exit_code(result: CycleResult) -> int:
    if result.execution and result.execution.errors:
        return 1
    return 0


def _ensure_env_template() -> None:
    """Create ``.env`` from ``.env.example`` when missing (no secrets)."""
    root = Path.cwd()
    env_path = root / ".env"
    example = root / ".env.example"
    if env_path.exists() or not example.exists():
        return
    env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        "Created .env from .env.example — add your Alpaca paper keys there "
        "for stock data (crypto works without keys).\n"
    )


def _print_bars_table(symbol: str, bars: list, *, asset: str) -> None:
    print(f"\n=== {asset}: {symbol} ({len(bars)} bars) ===")
    if not bars:
        print("  (no data)")
        return
    print(f"  {'date':<12}{'open':>12}{'high':>12}{'low':>12}{'close':>12}{'volume':>14}")
    for bar in bars:
        day = bar.timestamp.date()
        print(
            f"  {day!s:<12}"
            f"{bar.open:>12,.2f}"
            f"{bar.high:>12,.2f}"
            f"{bar.low:>12,.2f}"
            f"{bar.close:>12,.2f}"
            f"{bar.volume:>14,.2f}"
        )


def cmd_bars(
    cfg: Config,
    symbols: list[str],
    *,
    timeframe: str,
    limit: int,
) -> int:
    _ensure_env_template()
    crypto, stocks = partition_symbols(symbols)
    if not crypto and not stocks:
        print("Provide at least one symbol, e.g. BTC/USD or AAPL.", file=sys.stderr)
        return 1

    fetcher = AlpacaBarsFetcher(bars_config_from_env(cfg))
    try:
        if crypto:
            crypto_bars = fetcher.fetch_crypto(crypto, timeframe=timeframe, limit=limit)
            for sym in crypto:
                _print_bars_table(sym, crypto_bars.get(sym, []), asset="Crypto")

        if stocks:
            if not cfg.has_brokerage_creds:
                print(
                    "\nStock symbols requested but Alpaca keys are missing.\n"
                    "1. Open https://app.alpaca.markets/ and copy your paper API keys.\n"
                    "2. Edit .env and set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY.\n"
                    "3. Re-run: aoa bars " + " ".join(symbols),
                    file=sys.stderr,
                )
                return 1
            stock_bars = fetcher.fetch_stocks(stocks, timeframe=timeframe, limit=limit)
            for sym in stocks:
                _print_bars_table(sym, stock_bars.get(sym, []), asset="Stock")
    finally:
        fetcher.close()

    return 0


def cmd_doctor(cfg: Config, *, offline: bool = False) -> int:
    print(f"AOA Financial v0.2.0 — trading mode: {cfg.trading_mode.upper()}")
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
    if cfg.alpaca_auth_source:
        label = cfg.alpaca_auth_source
        if cfg.alpaca_cli_profile:
            label = f"{label} (profile {cfg.alpaca_cli_profile})"
        print(f"  ✓ Alpaca auth: {label}")
    if offline or cfg.is_test:
        label = "Offline mode" if offline else "Test environment"
        print(f"  ✓ {label} — skipping broker/LLM connectivity checks.")
        return 0
    fetcher = AlpacaBarsFetcher(bars_config_from_env(cfg))
    try:
        crypto_bar = fetcher.verify_crypto("BTC/USD", limit=1)
        print(
            f"  ✓ Crypto bars API (no keys); BTC/USD last close "
            f"${crypto_bar.close:,.2f} ({crypto_bar.timestamp.date()})."
        )
    except BrokerError as exc:
        print(f"  ✗ Crypto bars check failed: {exc}")
        return 1
    finally:
        fetcher.close()
    if not cfg.has_brokerage_creds:
        print(
            "  · Stock bars need ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY in .env "
            "(crypto already works)."
        )
        print("  · Skipping broker account and stock-bar checks until keys are set.")
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


def cmd_assistant(cfg: Config) -> int:
    team = build_team(cfg)
    brief = team.run_assistant_brief()
    print("\n=== Alex — your priorities ===")
    print(f"Focus: {brief.focus}")
    print(brief.summary)
    for label, items in (
        ("MUST DO", brief.must_do),
        ("SHOULD DO", brief.should_do),
        ("CAN WAIT", brief.can_wait),
    ):
        if items:
            print(f"\n{label}:")
            for item in items:
                hint = f" → {item.action_hint}" if item.action_hint else ""
                print(f"  • {item.title}: {item.detail}{hint}")
    return 0


def cmd_team_promote(cfg: Config) -> int:
    team = build_team(cfg)
    if team.analytics is None:
        print("Analytics disabled — set AOA_ANALYTICS_ENABLED=1 to store proposals.")
        return 1
    print("\n=== Team promotions — each lead is proposing a sub-team ===\n")
    proposals = team.propose_team_expansions()
    for p in proposals:
        print(f"{p.lead_name} → {p.promotion_title}")
        print(f"  Team: {p.team_name}")
        print(f"  Mission: {p.mission}")
        if p.expansion_rationale:
            print(f"  Why: {p.expansion_rationale}")
        for m in p.members:
            resp = ", ".join(m.responsibilities)
            print(f"    • {m.name} ({m.role}): {resp}")
        print()
    print(f"{len(proposals)} proposals sent for your review.")
    print("Edit or approve in the dashboard → Promotions tab, or via the API.")
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


def _print_workloop_result(result, *, approver: str = "Aaron") -> None:
    run = result.run
    required = (run.team_review or {}).get("required_approver") or approver
    print("\n=== Work-loop summary ===")
    print(f"Run: {run.run_id} | stage: {run.stage} | status: {run.status}")
    if run.discovered:
        kinds = sorted({s.get('kind', '') for s in run.discovered})
        print(f"Discovered {len(run.discovered)} source(s): {', '.join(kinds)}")
    if run.adaptations:
        actions = run.adaptations[-1].get("actions", [])
        if actions:
            print("Recommended adaptations:")
            for action in actions:
                print(f"  • {action}")
    if run.proposal:
        print(f"Proposal: {run.proposal.get('summary', '')}")
    if run.team_review:
        print(
            "Team review: "
            f"{run.team_review.get('verdict', 'n/a')} — "
            f"{run.team_review.get('summary', '')}"
        )
        print(f"Required approver: {required}")
    if run.approval:
        print(
            f"Approval: {run.approval.get('approver')} at {run.approval.get('approved_at', 'n/a')}"
        )
    if run.verify:
        flag = "PASS" if run.verify.get("passed") else "FAIL"
        print(f"Verify: {flag}")
    if run.upgrade:
        flag = "OK" if run.upgrade.get("ok", True) else "FAIL"
        print(f"Upgrade: {flag}")
    if run.reverify:
        flag = "PASS" if run.reverify.get("passed") else "FAIL"
        print(f"Re-verify: {flag}")
    if run.merge:
        print(f"Merge: {run.merge.get('message', '')}")
    if run.error:
        print(f"Note: {run.error}")
    for note in run.notes:
        print(f"  - {note}")
    if result.halted and run.status == "awaiting_approval":
        print(
            f"\nAwaiting approval from {required}. "
            f"Run: aoa workloop approve --approver {required}"
        )
    elif result.halted and run.status == "rejected_by_team":
        print("\nChange rejected by the team — fix issues and start a new run.")


def cmd_workloop_run(
    cfg: Config,
    *,
    from_stage: str | None,
    dry_run: bool,
    resume: bool,
) -> int:
    if not cfg.workloop_enabled:
        print("Work-loop is disabled (AOA_WORKLOOP_ENABLED=false).")
        return 1
    orch = WorkloopOrchestrator(cfg)
    print(f"Work-loop at {cfg.workloop_path}")
    result = orch.run(from_stage=from_stage, dry_run=dry_run, resume=resume)
    _print_workloop_result(result, approver=cfg.workloop_approver)
    if result.run.status == "failed":
        return 1
    if result.halted:
        return 2
    return 0


def cmd_workloop_status(cfg: Config) -> int:
    orch = WorkloopOrchestrator(cfg)
    run = orch.status()
    sched = build_scheduler(cfg).state()
    print(f"Scheduler: iteration={sched.iteration} status={sched.status}")
    if sched.last_completed_at:
        print(f"Last completed: {sched.last_completed_run_id} at {sched.last_completed_at}")
    if sched.next_run_at:
        print(f"Next run scheduled: {sched.next_run_at}")
    if run is None:
        print("No active work-loop run.")
        return 0
    print(f"Run: {run.run_id}")
    print(f"Stage: {run.stage}")
    print(f"Status: {run.status}")
    if run.iteration:
        print(f"Iteration: {run.iteration}")
    if run.previous_run_id:
        print(f"Previous run: {run.previous_run_id}")
    if run.error:
        print(f"Error: {run.error}")
    return 0


def cmd_workloop_loop(cfg: Config, *, dry_run: bool) -> int:
    if not cfg.workloop_enabled:
        print("Work-loop is disabled (AOA_WORKLOOP_ENABLED=false).")
        return 1
    scheduler = build_scheduler(cfg)
    print(
        f"Work-loop scheduler at {cfg.workloop_path} "
        f"(interval={cfg.workloop_interval_seconds}s). Ctrl-C to stop."
    )
    try:
        scheduler.run_forever(dry_run=dry_run)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_workloop_approve(cfg: Config, *, approver: str, note: str) -> int:
    orch = WorkloopOrchestrator(cfg)
    approval = orch.approve(approver=approver, note=note)
    print(
        f"Recorded approval from {approval['approver']} for run {approval['run_id']}."
    )
    return 0


def cmd_workloop_log(cfg: Config, n: int) -> int:
    from aoa.workloop.store import WorkloopStore

    entries = WorkloopStore(cfg.workloop_path).tail(n)
    if not entries:
        print("Work-loop log is empty.")
        return 0
    for e in entries:
        print(f"{e.get('ts', '')}  {e.get('event', '')}")
    return 0


def _print_repair_result(result) -> None:
    run = result.run
    print(f"\n=== Fable 5 repair triage ({run.run_id}) ===")
    print(f"Queue: {result.queue_path}")
    if not run.items:
        print("No repair candidates — system looks healthy.")
        return
    for item in run.items:
        flag = "FIX" if item.fixable else "WATCH"
        print(f"  [{flag}] {item.title} ({item.source}, {item.severity})")
        if item.detail:
            print(f"        {item.detail[:120]}")


def cmd_repair_triage(cfg: Config, *, no_sync: bool) -> int:
    if not cfg.repair_enabled:
        print("Repair loop is disabled (AOA_REPAIR_ENABLED=false).")
        return 0
    orch = RepairOrchestrator(cfg)
    result = orch.triage(sync_state=not no_sync)
    _print_repair_result(result)
    if cfg.repair_sync_state and not no_sync:
        print(f"STATE.md updated at {result.state_path}")
    return 1 if any(i.severity == "critical" and i.fixable for i in result.run.items) else 0


def cmd_repair_queue(cfg: Config) -> int:
    orch = RepairOrchestrator(cfg)
    items = orch.queue()
    if not items:
        print("Repair queue is empty. Run: aoa repair triage")
        return 0
    for item in items:
        print(f"{item.item_id}  [{item.status}] {item.title} ({item.severity})")
    return 0


def cmd_repair_worktree(cfg: Config, *, item_id: str) -> int:
    orch = RepairOrchestrator(cfg)
    info = orch.prepare_worktree(item_id=item_id or None)
    if not info.get("ok"):
        print(f"Worktree failed: {info.get('error', 'unknown')}", file=sys.stderr)
        return 1
    print(f"Repair worktree: {info['path']} (branch {info['branch']})")
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


def cmd_burnin(cfg: Config, *, cycles: int, pause: int) -> int:
    """Run multiple team cycles for paper-trading validation."""
    if cfg.alpaca_live and not cfg.dry_run:
        print(
            "Warning: burn-in on a live account — set AOA_PROFILE=paper-dry or "
            "AOA_DRY_RUN=true for validation.",
            file=sys.stderr,
        )
    team = build_team(cfg)
    _print_environment(cfg)
    journal = Journal(cfg.journal_path)
    start_count = len(journal.read_all())
    halted = 0
    exec_errors = 0

    print(
        f"Burn-in: {cycles} cycle(s), pause={pause}s, mode={cfg.trading_mode}, "
        f"trading_agents={'on' if cfg.trading_agents_enabled else 'off'}"
    )
    for i in range(1, cycles + 1):
        print(f"\n--- Burn-in cycle {i}/{cycles} ---")
        if not team.broker.is_market_open():
            print("Market closed — running analysis anyway.")
        result = team.run_cycle()
        _print_team(result)
        save_signal_adapter(cfg, team.trading.signal_adapter)
        if result.halted:
            halted += 1
        elif result.cycle and _cycle_exit_code(result.cycle):
            exec_errors += 1
        if i < cycles and pause > 0:
            time.sleep(pause)

    summary = summarize_journal(journal.read_all()[start_count:])
    print("\n=== Burn-in summary ===")
    print(f"Cycles completed: {summary.cycles}  halted: {halted}  exec errors: {exec_errors}")
    print(
        f"Orders: submitted={summary.orders_submitted} dry-run={summary.dry_runs} "
        f"errors={summary.errors} re-entry skips={summary.reentry_skips}"
    )
    if cfg.trading_agents_enabled:
        print(
            f"TradingAgents: debates={summary.research_debates} "
            f"risk_debates={summary.risk_debates} "
            f"fund_manager={summary.fund_manager_reviews}"
        )
    if summary.blocked:
        print(f"Risk-blocked proposals: {len(summary.blocked)}")
    return 1 if halted or exec_errors else 0


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
    sub.add_parser("assistant", help="Alex — prioritized must-do vs should-do brief.")
    team = sub.add_parser("team", help="Team-specific commands.")
    team_sub = team.add_subparsers(dest="team_command", required=True)
    team_sub.add_parser("health", help="Run Bob's health and code-integrity checks.")
    team_sub.add_parser("brief", help="Run Tom→Julie→Morgan→Alan brief without trading.")
    team_sub.add_parser("assistant", help="Alex — prioritized must-do vs should-do brief.")
    team_sub.add_parser(
        "promote",
        help="Each lead proposes a sub-team for your approval.",
    )
    sub.add_parser("serve", help="Start the web dashboard and REST API.")
    jp = sub.add_parser("journal", help="Tail the decision/trade journal.")
    jp.add_argument("-n", type=int, default=20, help="Number of entries to show.")
    sub.add_parser("report", help="Summarize activity and live P&L.")
    bp = sub.add_parser(
        "burnin",
        help="Run N paper cycles and print a burn-in summary.",
    )
    bp.add_argument(
        "-n", "--cycles", type=int, default=10, help="Number of cycles (default 10)."
    )
    bp.add_argument(
        "--pause",
        type=int,
        default=0,
        help="Seconds between cycles (default: AOA_CYCLE_SECONDS or 60).",
    )

    bars_p = sub.add_parser(
        "bars",
        help="Fetch recent stock and/or crypto OHLCV bars (crypto needs no keys).",
    )
    bars_p.add_argument(
        "symbols",
        nargs="+",
        help="Tickers or crypto pairs, e.g. BTC/USD AAPL.",
    )
    bars_p.add_argument(
        "--timeframe",
        default="1Day",
        help="Bar interval (default 1Day). Examples: 1Hour, 15Min.",
    )
    bars_p.add_argument(
        "--limit",
        type=int,
        default=7,
        help="Number of recent bars per symbol (default 7).",
    )

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

    wl = sub.add_parser("workloop", help="Autonomous discover→merge improvement loop.")
    wl_sub = wl.add_subparsers(dest="workloop_command", required=True)
    wl_run = wl_sub.add_parser("run", help="Run the work loop.")
    wl_run.add_argument(
        "--from",
        dest="from_stage",
        choices=list(STAGE_ORDER),
        help="Start at a specific stage.",
    )
    wl_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Bypass approval and skip execute/upgrade/merge side effects.",
    )
    wl_run.add_argument(
        "--resume",
        action="store_true",
        help="Resume the last saved run (e.g. after approval).",
    )
    wl_loop = wl_sub.add_parser(
        "loop",
        help="Run work loops continuously at AOA_WORKLOOP_INTERVAL_SECONDS.",
    )
    wl_loop.add_argument(
        "--dry-run",
        action="store_true",
        help="Bypass approval and skip execute/upgrade/merge side effects.",
    )
    wl_sub.add_parser("status", help="Show the current work-loop run state.")
    wl_approve = wl_sub.add_parser("approve", help="Record approver sign-off.")
    wl_approve.add_argument(
        "--approver",
        default=None,
        help="Approver name (defaults to AOA_WORKLOOP_APPROVER).",
    )
    wl_approve.add_argument("--note", default="", help="Optional approval note.")
    wl_log = wl_sub.add_parser("log", help="Tail the work-loop audit log.")
    wl_log.add_argument("-n", type=int, default=20, help="Number of entries to show.")

    rp = sub.add_parser(
        "repair",
        help="Fable 5 repair loop — discover issues, queue fixes, isolated worktrees.",
    )
    rp_sub = rp.add_subparsers(dest="repair_command", required=True)
    rp_triage = rp_sub.add_parser("triage", help="Scan audits/verify/STATE.md and refresh queue.")
    rp_triage.add_argument(
        "--no-sync",
        action="store_true",
        help="Do not rewrite STATE.md from discovery results.",
    )
    rp_sub.add_parser("queue", help="Show the current repair queue.")
    rp_wt = rp_sub.add_parser("worktree", help="Create an isolated git worktree for a fix.")
    rp_wt.add_argument("--item-id", default="", help="Repair item id (optional).")

    args = parser.parse_args(argv)
    _ensure_env_template()
    cfg = Config.from_env()

    try:
        if args.command == "bars":
            return cmd_bars(cfg, args.symbols, timeframe=args.timeframe, limit=args.limit)
        if args.command == "doctor":
            return cmd_doctor(cfg, offline=getattr(args, "offline", False))
        if args.command == "status":
            return cmd_status(cfg)
        if args.command == "run":
            return cmd_run(cfg)
        if args.command == "loop":
            return cmd_loop(cfg)
        if args.command == "assistant":
            return cmd_assistant(cfg)
        if args.command == "team":
            if args.team_command == "health":
                return cmd_team_health(cfg)
            if args.team_command == "brief":
                return cmd_team_brief(cfg)
            if args.team_command == "assistant":
                return cmd_assistant(cfg)
            if args.team_command == "promote":
                return cmd_team_promote(cfg)
        if args.command == "serve":
            return cmd_serve(cfg)
        if args.command == "journal":
            return cmd_journal(cfg, args.n)
        if args.command == "report":
            return cmd_report(cfg)
        if args.command == "burnin":
            pause = args.pause or cfg.cycle_seconds or 60
            return cmd_burnin(cfg, cycles=max(1, args.cycles), pause=pause)
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
        if args.command == "workloop":
            if args.workloop_command == "run":
                return cmd_workloop_run(
                    cfg,
                    from_stage=getattr(args, "from_stage", None),
                    dry_run=getattr(args, "dry_run", False),
                    resume=getattr(args, "resume", False),
                )
            if args.workloop_command == "loop":
                return cmd_workloop_loop(cfg, dry_run=getattr(args, "dry_run", False))
            if args.workloop_command == "status":
                return cmd_workloop_status(cfg)
            if args.workloop_command == "approve":
                approver = args.approver or cfg.workloop_approver
                return cmd_workloop_approve(cfg, approver=approver, note=args.note)
            if args.workloop_command == "log":
                return cmd_workloop_log(cfg, args.n)
        if args.command == "repair":
            if args.repair_command == "triage":
                return cmd_repair_triage(cfg, no_sync=getattr(args, "no_sync", False))
            if args.repair_command == "queue":
                return cmd_repair_queue(cfg)
            if args.repair_command == "worktree":
                return cmd_repair_worktree(cfg, item_id=getattr(args, "item_id", ""))
    except (BrokerError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
