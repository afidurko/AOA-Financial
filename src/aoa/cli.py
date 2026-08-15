"""Command-line interface for the AOA Financial swarm.

Commands:
  aoa bars       Fetch recent OHLCV bars (Moomoo OpenD or Alpaca).
  aoa doctor     Validate configuration & connectivity.
  aoa setup      One-time setup (mac, moomoo, …).
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
  aoa hft        Offline HFT/L2 lanes: hftbacktest + vendored orderbook.
  aoa visualhft  Offline VisualHFT microstructure studies (research lane).
  aoa avellaneda Offline Avellaneda–Stoikov market-making research lane.
  aoa microstructure  Mesh status for all offline HFT/LOB research lanes.
  aoa workspaces Companion workspace mesh (OpenStock, QM, VisualHFT, hftbacktest).
  aoa workloop   Run the autonomous discover→merge improvement loop.
  aoa repair     Fable 5 repair loop — discover issues and queue fixes.
  aoa vault      Sync schema-driven vault property notes.
  aoa study      Study cortex — learn DE/physics/econ bridges, use, export.
  aoa hftish     Order-book imbalance research lane (example-hftish patterns).
  aoa tasks      Loop prompt shortkeys and deterministic task runners.
  aoa attl       Agentic Task-Team Loop (auto-12, brain mesh, critical-only).
  aoa integrity  Integrity Ten — continuous code/workspace/neural/mesh checks.
  aoa burnin     Run N paper cycles and print a burn-in summary.
"""

from __future__ import annotations

import argparse
import json
import subprocess
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
from aoa.brokerage.moomoo import MoomooBroker
from aoa.config import Config
from aoa.data.news import AlpacaNewsFeed, MoomooNewsFeed, NewsFeed, NullNewsFeed
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient, LLMError, llm_from_config
from aoa.repair.orchestrator import RepairOrchestrator
from aoa.reporting import position_pnl, summarize_journal
from aoa.simulation.live import LiveMarketTracker
from aoa.simulation.scenarios import extract_scenario, list_scenarios
from aoa.simulation.simulator import MarketSimulator, SimulationConfig
from aoa.simulation.trends import analyze_trends
from aoa.state import StateStore
from aoa.swarm.orchestrator import CycleResult, Orchestrator
from aoa.team.orchestrator import TeamCycleResult, TeamOrchestrator
from aoa.vault.sync import sync_vault_engineering, vault_status
from aoa.version import package_version
from aoa.workloop.models import STAGE_ORDER
from aoa.workloop.orchestrator import WorkloopOrchestrator
from aoa.workloop.scheduler import build_scheduler


def build_broker(cfg: Config) -> Broker:
    if cfg.broker == "moomoo":
        return MoomooBroker.from_config(cfg)
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
    return llm_from_config(cfg)


def build_news(cfg: Config) -> NewsFeed:
    if not cfg.news_enabled:
        return NullNewsFeed()
    if cfg.broker == "moomoo":
        try:
            return MoomooNewsFeed(
                host=cfg.moomoo_opend_host,
                port=cfg.moomoo_opend_port,
                connect_timeout=cfg.moomoo_connect_timeout,
            )
        except BrokerError:
            # OpenD down — keep the swarm running without headlines.
            return NullNewsFeed()
    if not cfg.has_brokerage_creds:
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
        return_scale=cfg.adapt_return_scale,
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
    print(
        f"Swarm memory: plasticity={'ON' if cfg.plasticity_enabled else 'OFF'} | "
        f"study_usage={'ON' if cfg.study_usage_enabled else 'OFF'} "
        f"(limit={cfg.study_usage_limit}) | "
        f"trading_agents={'ON' if cfg.trading_agents_enabled else 'OFF'} | "
        f"adapt={'ON' if cfg.adapt_enabled else 'OFF'}"
    )


def _print_swarm_memory_config(cfg: Config) -> None:
    """Report plasticity / study / TradingAgents / adapt configuration."""
    if cfg.plasticity_enabled:
        print(
            f"  ✓ Plasticity ON (tail={cfg.plasticity_tail}, "
            f"max_lessons={cfg.plasticity_max_lessons}, path={cfg.plasticity_path})"
        )
    else:
        print("  · Plasticity OFF (set AOA_PLASTICITY_ENABLED=true to enable).")
    if cfg.study_usage_enabled:
        from aoa.study.cortex import StudyCortex

        status = StudyCortex.from_config(cfg).status()
        baseline = "baseline+mastered" if cfg.study_usage_baseline else "mastered-only"
        print(
            f"  ✓ Study cortex usage ALWAYS ON "
            f"(mode={baseline}, mastered={status['n_mastered']}/{status['n_cards']}, "
            f"due={status['n_due']}, limit={cfg.study_usage_limit}, "
            f"path={cfg.study_path})"
        )
        if status["n_mastered"] == 0 and cfg.study_usage_baseline:
            print("  · Bridge baselines inject every cycle; drill to raise mastery weights.")
    else:
        print("  · Study cortex usage OFF (set AOA_STUDY_USAGE_ENABLED=true to enable).")
    if cfg.trading_agents_enabled:
        print(
            f"  ✓ TradingAgents ON (debate_rounds={cfg.trading_agents_debate_rounds})"
        )
    else:
        print("  · TradingAgents OFF (set AOA_TRADING_AGENTS_ENABLED=true to enable).")
    if cfg.adapt_enabled:
        adapter = build_signal_adapter(cfg)
        print(
            f"  ✓ Low-rank signal adaptation ON "
            f"(rank={cfg.adapt_rank}, alpha={cfg.adapt_alpha}, "
            f"updates so far={adapter.updates if adapter else 0}, path={cfg.adapt_path})"
        )
    else:
        print("  · Low-rank signal adaptation OFF (set AOA_ADAPT_ENABLED=true to enable).")


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
    if result.short_term:
        print("\n=== Jim — short-term technical overlays ===")
        for j in result.short_term:
            print(
                f"  {j.symbol:<6} {j.direction.value:<8} conv={j.conviction:.2f}  "
                f"ret={j.expected_return:+.2%}  {j.rationale[:50]}"
            )
    if result.company_analyses:
        print("\n=== Cindy — company profitability ===")
        for c in result.company_analyses:
            print(
                f"  {c.symbol:<6} grade={c.profitability_grade:<3} q={c.quality_score:+.2f}  "
                f"fv={c.fair_value}  {c.thesis[:50]}"
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
        "Created .env from .env.example — defaults are Moomoo + local WASTE LLM.\n"
        "  Start OpenD (127.0.0.1:11111) and WASTE serve (:8000), then: aoa doctor\n"
        "  Guide: docs/how-to/moomoo-setup.md · docs/how-to/waste-local-llm.md\n"
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

    if cfg.broker == "moomoo":
        if crypto:
            print(
                "Crypto pairs are not available via Moomoo OpenD in AOA; "
                "omit them or set AOA_BROKER=alpaca for crypto bars.",
                file=sys.stderr,
            )
            if not stocks:
                return 1
        if stocks:
            try:
                with build_broker(cfg) as broker:
                    for sym in stocks:
                        bars = broker.get_bars(sym, timeframe=timeframe, limit=limit)
                        _print_bars_table(sym, bars, asset="Stock")
            except BrokerError as exc:
                print(f"Moomoo bars failed: {exc}", file=sys.stderr)
                return 1
        return 0

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
    print(f"AOA Financial v{package_version()} — trading mode: {cfg.trading_mode.upper()}")
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
    print(f"  ✓ Broker: {cfg.broker} | bar feed: {cfg.bar_feed} | news limit: {cfg.news_limit}")
    if cfg.openstock_url:
        print(f"  ✓ OpenStock link: {cfg.openstock_url}")
    if cfg.qm_url:
        print(f"  ✓ QM harness link: {cfg.qm_url}")
    if cfg.visualhft_url:
        print(f"  ✓ VisualHFT link: {cfg.visualhft_url}")
    if cfg.broker == "moomoo":
        print(
            f"  ✓ Moomoo OpenD target: {cfg.moomoo_opend_host}:{cfg.moomoo_opend_port} "
            f"({cfg.moomoo_market}, {'live' if cfg.moomoo_live else 'simulate'})"
        )
        if cfg.news_enabled:
            print("  · News feed: Moomoo headlines not wired yet (NullNewsFeed).")
    elif cfg.alpaca_auth_source:
        label = cfg.alpaca_auth_source
        if cfg.alpaca_cli_profile:
            label = f"{label} (profile {cfg.alpaca_cli_profile})"
        print(f"  ✓ Alpaca auth: {label}")
    _print_swarm_memory_config(cfg)
    if offline or cfg.is_test:
        label = "Offline mode" if offline else "Test environment"
        print(f"  ✓ {label} — skipping broker/LLM connectivity checks.")
        return 0
    if cfg.broker == "alpaca":
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
        if cfg.broker == "moomoo":
            print(
                f"  ✓ Live bars API; SPY last close ${latest.close:,.2f} "
                f"({latest.timestamp.date()})."
            )
            print("  · News: Moomoo OpenD get_search_news (moomooapi skill).")
        else:
            feed = cfg.alpaca_data_feed or cfg.bar_feed
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
        base = f", base_url={cfg.llm_base_url}" if cfg.llm_provider == "openai_compatible" else ""
        print(f"  ✓ LLM client initialized (provider={cfg.llm_provider}{base}).")
        llm.ping()
        print(f"  ✓ LLM reachable (model={cfg.model}).")
    except LLMError as exc:
        print(f"  ✗ LLM check failed: {exc}")
        return 1
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


def cmd_loop_brief(cfg: Config, *, push: bool, as_json: bool) -> int:
    from aoa.loop.user_brief import (
        build_loop_user_brief,
        deliver_loop_brief,
        repair_queue_summary,
    )

    team = build_team(cfg)
    assistant = team.run_assistant_brief()
    pending: list[dict] = []
    if team.analytics is not None:
        pending = team.analytics.store.list_pending_responses()
    brief = build_loop_user_brief(
        assistant_brief=assistant,
        repair_summary=repair_queue_summary(cfg.repair_path),
        pending_responses=pending,
    )

    if as_json:
        print(json.dumps(brief.to_context(), indent=2, default=str))
    else:
        print("\n=== Loop brief — trading + engineering ===")
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
                    hint = f" → {item['action_hint']}" if item.get("action_hint") else ""
                    print(f"  • {item['title']}: {item['detail']}{hint}")
        if brief.suggested_replies:
            print("\nAWAITING YOUR REPLY:")
            for reply in brief.suggested_replies:
                print(f"  • {reply.prompt} (id {reply.target})")

    if push:
        notifier = team.aaron.notifier
        if not notifier.configured:
            print(
                "\niPhone push not configured — set AOA_CUSTOM_APP_WEBHOOK_URL "
                "(or Pushover / ntfy) to deliver.",
                file=sys.stderr,
            )
            return 1
        channels = deliver_loop_brief(brief, notifier)
        print(f"\nBrief delivered via: {', '.join(channels)}")
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


def cmd_hft_status(*, as_json: bool) -> int:
    from aoa.hftbacktest import probe_status as probe_hft
    from aoa.orderbook import probe_status as probe_book

    hft = probe_hft()
    book = probe_book()
    payload = {"hftbacktest": hft, "orderbook": book, "offline_only": True}
    if as_json:
        print(json.dumps(payload, indent=2))
        # Book lane is vendored and must be healthy; hftbacktest remains optional.
        return 0 if book.get("ok") else 1
    print("=== HFT research lanes (offline) ===")
    print("--- hftbacktest ---")
    print(f"  installed: {hft['installed']}")
    print(f"  version:   {hft.get('version') or '—'}")
    print(f"  engine:    {hft.get('engine') or '—'}")
    print(f"  upstream:  {hft.get('upstream')}")
    if not hft["installed"]:
        print(f"  install:   {hft.get('hint')}")
    else:
        print(f"  next:      {hft.get('hint')}")
    print("--- orderbook (HFT-Orderbook) ---")
    print(f"  ok:        {book.get('ok')}")
    print(f"  engine:    {book.get('engine')}")
    print(f"  impl:      {book.get('implementation')}")
    print(f"  upstream:  {book.get('upstream')}")
    print(f"  next:      {book.get('hint')}")
    return 0 if book.get("ok") else 1


def cmd_hft_book_smoke(*, as_json: bool) -> int:
    from aoa.orderbook import run_book_smoke

    result = run_book_smoke()
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("=== HFT orderbook smoke (vendored LOB) ===")
        print(f"  ok:         {result.ok}")
        print(f"  best bid:   {result.best_bid}")
        print(f"  best ask:   {result.best_ask}")
        print(f"  bid volume: {result.bid_volume}")
        print(f"  ask volume: {result.ask_volume}")
        print(f"  orders:     {result.order_count}  levels={result.levels}")
        print(f"  detail:     {result.detail}")
    return 0 if result.ok else 1


def cmd_hft_smoke(
    *,
    n_events: int,
    steps: int,
    seed: int,
    as_json: bool,
) -> int:
    from aoa.hftbacktest import HAS_HFTBACKTEST, run_npz_smoke

    if not HAS_HFTBACKTEST:
        msg = 'hftbacktest not installed. Run: pip install -e ".[hftbacktest]"'
        if as_json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(msg, file=sys.stderr)
        return 1
    result = run_npz_smoke(n_events=n_events, steps=steps, seed=seed)
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("=== HFT synthetic L2 smoke ===")
        print(f"  ok:        {result.ok}")
        print(f"  steps:     {result.steps}")
        print(f"  best bid:  {result.best_bid}")
        print(f"  best ask:  {result.best_ask}")
        print(f"  position:  {result.position}")
        print(f"  events:    {result.n_events}  seed={result.seed}")
        print(f"  detail:    {result.detail}")
    return 0 if result.ok else 1


def cmd_hft_run(
    *,
    data: str,
    tick_size: float,
    lot_size: float,
    steps: int,
    step_ns: int,
    as_json: bool,
) -> int:
    """Advance an on-disk hftbacktest feed without placing orders (offline probe)."""
    from aoa.hftbacktest import HAS_HFTBACKTEST
    from aoa.hftbacktest.runner import load_npz_from_npz

    if not HAS_HFTBACKTEST:
        msg = 'hftbacktest not installed. Run: pip install -e ".[hftbacktest]"'
        if as_json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(msg, file=sys.stderr)
        return 1
    path = Path(data)
    if not path.exists():
        msg = f"data file not found: {path}"
        if as_json:
            print(json.dumps({"ok": False, "error": msg}))
        else:
            print(msg, file=sys.stderr)
        return 1

    hbt = load_npz_from_npz(
        str(path), tick_size=tick_size, lot_size=lot_size
    )
    try:
        advanced = 0
        for _ in range(steps):
            if hbt.elapse(step_ns) != 0:
                break
            advanced += 1
        depth = hbt.depth(0)
        payload = {
            "ok": advanced > 0,
            "data": str(path),
            "steps": advanced,
            "best_bid": float(depth.best_bid),
            "best_ask": float(depth.best_ask),
            "position": float(hbt.position(0)),
            "offline_only": True,
        }
    finally:
        hbt.close()

    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"=== HFT feed probe: {path.name} ===")
        print(f"  steps:     {payload['steps']}")
        print(f"  best bid:  {payload['best_bid']}")
        print(f"  best ask:  {payload['best_ask']}")
        print(f"  position:  {payload['position']}")
    return 0 if payload["ok"] else 1


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


def cmd_visualhft_status(*, as_json: bool) -> int:
    from aoa.visualhft import probe_status

    status = probe_status()
    if as_json:
        print(json.dumps(status, indent=2))
        return 0
    print("=== VisualHFT research lane ===")
    print(f"  available:  {status['available']}")
    print(f"  runtime:    {status['runtime']}")
    print(f"  desktop:    {status['desktop_host']}")
    print(f"  studies:    {', '.join(status['studies_ported'])}")
    print(f"  offline:    {status.get('offline_only', True)}")
    print(f"  never_live: {status.get('never_live', True)}")
    print(f"  fork:       {status['fork']}")
    print(f"  upstream:   {status['upstream']}")
    print(f"  next:       {status.get('hint')}")
    return 0


def cmd_visualhft_smoke(*, n_trades: int, seed: int, as_json: bool) -> int:
    from aoa.visualhft import run_synthetic_smoke

    try:
        result = run_synthetic_smoke(n_trades=n_trades, seed=seed)
    except ValueError as exc:
        if as_json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(str(exc), file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("=== VisualHFT synthetic smoke ===")
        print(f"  ok:        {result.ok}")
        print(f"  lob imb:   {result.lob_imbalance:.4f}")
        print(f"  vpin:      {result.vpin:.4f}")
        print(f"  otr:       {result.order_to_trade_ratio:.4f}")
        print(f"  mid:       {result.mid_price}")
        print(f"  trades:    {result.n_trades}")
        print(f"  buckets:   {result.vpin_buckets}")
        print(f"  seed:      {result.seed}")
    return 0 if result.ok else 1


def cmd_visualhft_studies(*, as_json: bool, ported_only: bool) -> int:
    from aoa.visualhft import list_studies

    rows = list_studies(ported_only=ported_only)
    payload = {"studies": rows, "count": len(rows), "ported_only": ported_only}
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0
    print("=== VisualHFT studies ===")
    for row in rows:
        flag = "ported" if row.get("ported") else "desktop-only"
        print(f"  {row['id']:24} [{flag}] {row['title']}")
        print(f"    {row['summary']}")
    return 0


def cmd_workspaces_status(*, as_json: bool) -> int:
    from aoa.workspaces import workspaces_report

    # Offline mesh probe — Config without creating .env side effects.
    cfg = Config.from_env(load_dotenv=False)
    report = workspaces_report(cfg)
    if as_json:
        print(json.dumps(report, indent=2))
        return 0
    print("=== Companion workspaces ===")
    print(f"  linked:  {report['linked']}/{report['count']}")
    print(f"  present: {report['present']}/{report['count']}")
    print("  live:    never (mesh is link/status only)")
    for row in report["workspaces"]:
        link = "linked" if row["linked"] else "unlinked"
        path = "present" if row["present"] else "missing"
        print(f"  · {row['id']:12} [{link}, {path}] {row['title']}")
        print(f"      {row['role']}")
        if row["url"]:
            print(f"      url: {row['url']}")
        print(f"      path: {row['local_path']}")
        print(f"      docs: {row['docs']}")
        if not row["present"] and row.get("setup"):
            print(f"      setup: {row['setup']}")
    return 0


def cmd_workspaces_setup() -> int:
    """Clone missing companion siblings via scripts/workspaces-setup-all.sh."""
    script = _repo_root() / "scripts" / "workspaces-setup-all.sh"
    if not script.is_file():
        print(f"Missing setup script: {script}", file=sys.stderr)
        return 1
    print(f"Running {script} …")
    proc = subprocess.run(["bash", str(script)], check=False)
    return int(proc.returncode)


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


def cmd_workloop_upgrade(_cfg: Config, *, dry_run: bool) -> int:
    from aoa.workloop.upgrade import run_upgrade_pipeline

    result = run_upgrade_pipeline(_repo_root(), dry_run=dry_run)
    flag = "OK" if result.get("ok") else "FAIL"
    mode = "dry-run" if dry_run else "upgrade"
    print(f"Workloop upgrade pipeline [{mode}]: {flag}")
    print(f"phase: {result.get('phase', '')}")
    if result.get("ok"):
        return 0
    upgrade = result.get("upgrade") or {}
    if upgrade.get("output"):
        print(str(upgrade["output"])[-500:])
    reverify = result.get("reverify") or {}
    if reverify and not reverify.get("passed"):
        print("Reverify failed after upgrade.")
    return 1


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


def cmd_repair_gate(cfg: Config, *, as_json: bool, mode: str) -> int:
    from aoa.repair.schedule_gate import GateAction, evaluate_gate

    repo_root = Path.cwd()
    for parent in [repo_root, *repo_root.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "aoa").is_dir():
            repo_root = parent
            break
    result = evaluate_gate(repo_root=repo_root, mode=mode)
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Gate action: {result.action.value}")
        print(f"Reason: {result.reason}")
        print(f"Mode: {mode}")
        print(f"L2 automation enabled: {result.l2_automation_enabled}")
        if result.fixable_items:
            print(f"Fixable items: {', '.join(result.fixable_items)}")
        print(f"Runs (24h): {result.runs_24h}")
        print(f"Tokens (24h): {result.tokens_24h}")
    if result.action is GateAction.PAUSE:
        return 2
    if result.action in {GateAction.TRIAGE_OK, GateAction.L2_ALLOWED}:
        return 0
    return 1


def cmd_repair_worktree(cfg: Config, *, item_id: str) -> int:
    orch = RepairOrchestrator(cfg)
    info = orch.prepare_worktree(item_id=item_id or None)
    if not info.get("ok"):
        print(f"Worktree failed: {info.get('error', 'unknown')}", file=sys.stderr)
        return 1
    print(f"Repair worktree: {info['path']} (branch {info['branch']})")
    return 0


def cmd_vault_sync(cfg: Config, *, dry_run: bool, as_json: bool) -> int:
    if not cfg.vault_sync_enabled:
        print("Vault sync is disabled (AOA_VAULT_SYNC_ENABLED=false).")
        return 0
    repo_root = Path.cwd()
    for parent in [repo_root, *repo_root.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "aoa").is_dir():
            repo_root = parent
            break
    effective_dry: bool | None = True if dry_run else None
    result = sync_vault_engineering(cfg, repo_root=repo_root, dry_run=effective_dry)
    if as_json:
        print(json.dumps(result.to_context(), indent=2))
    else:
        mode = "dry-run" if result.dry_run else "write"
        print(
            f"Vault sync ({mode}): scanned={result.notes_scanned} "
            f"updated={result.notes_updated} properties_changed={result.properties_changed}"
        )
        for note in result.note_results:
            if note.changed:
                keys = ", ".join(note.changed)
                print(f"  {note.path}: {keys}")
        for err in result.errors:
            print(f"  error: {err}", file=sys.stderr)
    return 0


def cmd_vault_status(cfg: Config, *, as_json: bool) -> int:
    repo_root = Path.cwd()
    for parent in [repo_root, *repo_root.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "aoa").is_dir():
            repo_root = parent
            break
    report = vault_status(cfg, repo_root=repo_root)
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Vault: {report['vault_root']}")
        print(f"Notes scanned: {report['notes_scanned']}")
        print(f"Stale notes: {report['stale_count']}")
        for row in report.get("stale_notes", []):
            keys = ", ".join(row.get("would_change", []))
            print(f"  {row['path']}: {keys}")
    return 0


def cmd_avellaneda_status(*, as_json: bool) -> int:
    from aoa.avellaneda_stoikov import probe_status

    status = probe_status()
    if as_json:
        print(json.dumps(status, indent=2))
        return 0
    print("=== Avellaneda–Stoikov research lane ===")
    print(f"  available: {status['available']}")
    print(f"  runtime:   {status['runtime']}")
    print(f"  model:     {status['model']}")
    print(f"  modes:     {', '.join(status['modes'])}")
    print(f"  offline:   {status.get('offline_only', True)}")
    print(f"  never_live:{status.get('never_live', True)}")
    print(f"  fork:      {status['fork']}")
    print(f"  docs:      {status.get('docs')}")
    print(f"  next:      {status.get('hint')}")
    return 0


def cmd_avellaneda_smoke(*, n_steps: int, n_sims: int, seed: int, as_json: bool) -> int:
    from aoa.avellaneda_stoikov import run_synthetic_smoke

    try:
        result = run_synthetic_smoke(n_steps=n_steps, n_sims=n_sims, seed=seed)
    except ValueError as exc:
        if as_json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("=== Avellaneda–Stoikov synthetic smoke ===")
        print(f"  ok:          {result.ok}")
        print(f"  reservation: {result.reservation:.4f}")
        print(f"  bid / ask:   {result.bid:.4f} / {result.ask:.4f}")
        print(f"  spread:      {result.spread:.4f}")
        print(f"  path PnL:    {result.final_pnl:.4f}")
        print(f"  mean PnL:    {result.mean_pnl:.4f} (n={result.n_sims})")
        print(f"  steps/seed:  {result.n_steps} / {result.seed}")
    return 0 if result.ok else 1


def cmd_avellaneda_simulate(
    *,
    n_steps: int,
    seed: int,
    ensemble: bool,
    n_sims: int,
    unlimited: bool,
    as_json: bool,
) -> int:
    from aoa.avellaneda_stoikov.simulate import SimConfig, run_ensemble, run_simulation

    limit_horizon = not unlimited
    if ensemble:
        payload = run_ensemble(
            n_sims=n_sims,
            seed=seed,
            n_steps=n_steps,
            limit_horizon=limit_horizon,
        )
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print("=== Avellaneda–Stoikov ensemble ===")
            print(f"  sims:     {payload['n_sims']}")
            print(f"  mean PnL: {payload['mean_pnl']:.4f}")
            print(f"  std PnL:  {payload['std_pnl']:.4f}")
            print(f"  min/max:  {payload['min_pnl']:.4f} / {payload['max_pnl']:.4f}")
            print(f"  horizon:  {'limited' if limit_horizon else 'unlimited'}")
        return 0

    result = run_simulation(
        SimConfig(n_steps=n_steps, seed=seed, limit_horizon=limit_horizon)
    )
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("=== Avellaneda–Stoikov path ===")
        print(f"  final PnL: {result.final_pnl:.4f}")
        print(f"  inventory: {result.final_inventory:.4f}")
        print(f"  cash:      {result.final_cash:.4f}")
        print(f"  mid:       {result.final_mid:.4f}")
        print(f"  q range: {result.min_inventory:.1f} … {result.max_inventory:.1f}")
        print(f"  horizon:   {'limited' if result.limit_horizon else 'unlimited'}")
        print(f"  seed:      {result.seed}")
    return 0


def cmd_microstructure_status(*, as_json: bool) -> int:
    from aoa.microstructure import catalog_status

    status = catalog_status()
    if as_json:
        print(json.dumps(status, indent=2))
        return 0
    print("=== Microstructure workspace mesh ===")
    print(f"  lanes:     {status['available_count']}/{status['lane_count']} available")
    print(f"  offline:   {status.get('offline_only', True)}")
    print(f"  never_live:{status.get('never_live', True)}")
    print(f"  docs:      {status.get('docs')}")
    for row in status.get("lanes", []):
        flag = "ok" if row.get("available") else "missing"
        print(f"  [{flag:7}] {row.get('lane')}: {row.get('hint')}")
        if not row.get("available") and row.get("error"):
            print(f"           {row['error']}")
    return 0


def _study_cortex(cfg: Config):
    from aoa.study.cortex import StudyCortex

    return StudyCortex.from_config(cfg, repo_root=_repo_root())


def cmd_study_status(cfg: Config, *, as_json: bool) -> int:
    status = _study_cortex(cfg).status()
    if as_json:
        print(json.dumps(status, indent=2))
        return 0
    print("=== Study cortex ===")
    print(f"Cards: {status['n_cards']} | due: {status['n_due']} | mastered: {status['n_mastered']}")
    print(f"Sessions: {status['sessions']} | updated: {status['updated_at'] or '(never)'}")
    print(f"Mastery file: {status['mastery_path']}")
    for field, bucket in status["by_field"].items():
        print(
            f"  {field}: {bucket['mastered']}/{bucket['total']} mastered, {bucket['due']} due"
        )
    if status["lessons"]:
        print("Recent lessons:")
        for lesson in status["lessons"][:5]:
            print(f"  - {lesson}")
    print(
        "Phases: learn (drill/grade) → use (AOA_STUDY_USAGE_ENABLED) → "
        "distill (aoa study export → LoRA/sLM)"
    )
    return 0


def cmd_study_drill(cfg: Config, *, n: int, field: str, reveal: bool, as_json: bool) -> int:
    items = _study_cortex(cfg).drill(n=n, field=field, include_answers=reveal)
    if as_json:
        print(json.dumps(items, indent=2))
        return 0
    if not items:
        print("No cards match that field.")
        return 1
    for i, item in enumerate(items, 1):
        due = "due" if item["due"] else "scheduled"
        print(f"--- {i}. {item['id']} [{item['field']}] ({due}, mastery {item['mastery']:.2f})")
        print(f"Title: {item['title']}")
        print(f"Drill: {item['drill_prompt']}")
        if reveal:
            print(f"Statement: {item['statement']}")
            print(f"Proof sketch:\n{item['proof_sketch']}")
            print(f"AOA mesh: {item['aoa_mesh']}")
        else:
            print(f"Reveal: aoa study show {item['id']}")
            print(f"Grade:  aoa study grade {item['id']} ok|miss")
        print()
    return 0


def cmd_study_show(cfg: Config, card_id: str, *, as_json: bool) -> int:
    data = _study_cortex(cfg).show(card_id, reveal=True)
    if data is None:
        print(f"Unknown card: {card_id}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(data, indent=2))
        return 0
    print(f"=== {data['id']}: {data['title']} ===")
    print(f"Field: {data['field']} | mastery: {data['mastery']:.2f}")
    print(f"\nStatement:\n{data['statement']}")
    print(f"\nProof sketch:\n{data['proof_sketch']}")
    print("\nApplications:")
    for app in data["applications"]:
        print(f"  - {app}")
    print(f"\nAOA mesh:\n{data['aoa_mesh']}")
    if data["bridges"]:
        print(f"\nBridges: {', '.join(data['bridges'])}")
    print(f"\nDrill:\n{data['drill_prompt']}")
    return 0


def cmd_study_grade(cfg: Config, card_id: str, result: str, *, note: str) -> int:
    passed = result.lower() in {"ok", "pass", "passed", "1", "true", "yes"}
    if result.lower() not in {
        "ok",
        "pass",
        "passed",
        "1",
        "true",
        "yes",
        "miss",
        "fail",
        "failed",
        "0",
        "false",
        "no",
    }:
        print("Result must be ok|miss (or pass|fail).", file=sys.stderr)
        return 1
    out = _study_cortex(cfg).grade(card_id, passed, note=note)
    if not out.get("ok"):
        print(out.get("error", "grade failed"), file=sys.stderr)
        return 1
    sched = out["schedule"]
    print(
        f"Graded {card_id}: {'ok' if passed else 'miss'} | "
        f"ease={sched['ease']:.2f} interval={sched['interval_days']:.1f}d "
        f"due={sched['due_at']}"
    )
    return 0


def cmd_study_usage(cfg: Config, *, as_json: bool) -> int:
    block = _study_cortex(cfg).to_usage_block(
        limit=cfg.study_usage_limit,
        baseline=cfg.study_usage_baseline,
    )
    if as_json:
        print(
            json.dumps(
                {
                    "usage_block": block,
                    "enabled": cfg.study_usage_enabled,
                    "baseline": cfg.study_usage_baseline,
                },
                indent=2,
            )
        )
        return 0
    if not cfg.study_usage_enabled:
        print("Swarm injection is OFF — set AOA_STUDY_USAGE_ENABLED=true (default is on).")
        return 1
    if not block:
        print("No usage meshes available (unexpected with baseline on).")
        return 1
    print(block)
    print("\n(always-on: injected into portfolio/risk prompts each cycle)")
    return 0


def cmd_study_export(cfg: Config, *, out: str, only_mastered: bool) -> int:
    path = Path(out) if out else cfg.data_dir / "study" / "corpus.jsonl"
    summary = _study_cortex(cfg).export_jsonl(path, only_mastered=only_mastered)
    print(
        f"Exported {summary['written']} pairs → {summary['path']} "
        f"(skipped {summary['skipped']})"
    )
    print("Next: fine-tune a small instruct model with aoa.adapt.torch_lora on this JSONL.")
    return 0


def cmd_study_sync(cfg: Config, *, as_json: bool) -> int:
    result = _study_cortex(cfg).sync_vault()
    if as_json:
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if not result.get("ok"):
        print(result.get("error", "sync failed"), file=sys.stderr)
        return 1
    print(f"Study vault sync: wrote {result['notes_written']} notes under {result['study_dir']}")
    return 0


def cmd_hftish_status(*, as_json: bool) -> int:
    """Show example-hftish companion wiring (research-only)."""
    root = _repo_root()
    sibling = root / "example-hftish"
    status = {
        "available": True,
        "module": "aoa.research.hftish_patterns",
        "companion": "example-hftish",
        "sibling_present": (sibling / ".git").is_dir()
        or (sibling / "tick_taker.py").is_file(),
        "sibling_path": str(sibling),
        "setup": "scripts/example-hftish-setup.sh",
        "docs": "docs/how-to/example-hftish-reference.md",
        "study_card": "bridge-hftish-imbalance",
        "mesh_algo": "algo.hftish_patterns",
        "consumers": [
            "julie.refine",
            "morgan.analyze_symbol",
            "SymbolSnapshot.to_context",
        ],
        "never_live": True,
        "hint": "aoa hftish smoke — offline follow/imbalance check (no broker)",
    }
    if as_json:
        print(json.dumps(status, indent=2))
        return 0
    print("=== example-hftish research lane ===")
    print(f"  module:    {status['module']}")
    print(
        f"  sibling:   {'present' if status['sibling_present'] else 'missing'} ({sibling})"
    )
    print(f"  mesh:      {status['mesh_algo']}")
    print(f"  study:     {status['study_card']}")
    print(f"  consumers: {', '.join(status['consumers'])}")
    print(f"  never_live:{status['never_live']}")
    print(f"  next:      {status['hint']}")
    return 0


def cmd_hftish_smoke(*, seed: int, as_json: bool) -> int:
    from aoa.research.hftish_patterns import synthetic_smoke

    result = synthetic_smoke(seed=seed)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print("=== example-hftish synthetic smoke ===")
        print(f"  ok:           {result['ok']}")
        print(f"  level_change: {result['level_change']}")
        print(f"  armed:        {result['armed']}")
        print(f"  follow:       {result['follow']}")
        diag = result.get("diagnosis") or {}
        print(f"  side:         {diag.get('side')}")
        print(f"  note:         {diag.get('note')}")
        print(f"  never_live:   {result.get('never_live', True)}")
    return 0 if result.get("ok") else 1


def _attl_orchestrator(cfg: Config):
    from aoa.attl.orchestrator import AttlOrchestrator
    from aoa.config import data_dir_for

    root = Path.cwd()
    return AttlOrchestrator(
        repo_root=root,
        data_dir=data_dir_for(cfg.env) / "attl",
    )


def cmd_attl_init(cfg: Config) -> int:
    orch = _attl_orchestrator(cfg)
    result = orch.init_workspace()
    print("ATTL init — auto-12")
    print(f"Brain: {result['brain']}")
    print(f"Mode: {result['mode']}")
    print(f"Roster ({len(result['roster'])}): {', '.join(result['roster'])}")
    print(f"Config: {result['config']}")
    return 0


def cmd_attl_status(cfg: Config, *, as_json: bool = False) -> int:
    orch = _attl_orchestrator(cfg)
    status = orch.status()
    if as_json:
        print(json.dumps(status, indent=2))
        return 0
    print(f"Mode: {status['mode']}  meshed={status.get('meshed')}")
    print(f"Review policy: {status['review_policy']}")
    print(f"Paused: {status.get('paused')}")
    print(f"Hard floor rules: {status.get('hard_floor_rules')}")
    print(f"Roster size: {status['roster_size']}")
    print(f"Pending tasks: {status['pending_tasks']}")
    brain = status.get("brain") or {}
    print(
        "Brain: "
        f"members={brain.get('members')} algos={brain.get('algorithms')} "
        f"required_ok={brain.get('required_ok')}"
    )
    return 0


def cmd_attl_roster(cfg: Config, *, as_json: bool = False) -> int:
    orch = _attl_orchestrator(cfg)
    rows = orch.roster()
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    print("Twelve-member meshed team")
    for i, row in enumerate(rows, 1):
        print(f"  {i:2}. {row['name']:8} — {row['role']}")
    return 0


def cmd_attl_propose(cfg: Config) -> int:
    orch = _attl_orchestrator(cfg)
    result = orch.propose()
    print(f"Reed proposed {result['count']} tasks (need-ordered)")
    if result.get("path"):
        print(f"Wrote: {result['path']}")
    for task in (result.get("tasks") or [])[:10]:
        flag = "auto" if task.get("automatable") else "human"
        print(f"  - [{flag}] {task.get('id')}: {task.get('title')}")
    return 0


def cmd_attl_brain_sync(cfg: Config, *, as_json: bool = False) -> int:
    orch = _attl_orchestrator(cfg)
    result = orch.brain_sync()
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return 0
    print(f"Nova sync ok={result.get('ok')}")
    print(f"Capture: {result.get('capture')}")
    stats = result.get("stats") or {}
    print(f"Stats: {stats}")
    return 0 if result.get("ok") else 1


def _ship_agent():
    from aoa.loop.prompts import find_repo_root
    from aoa.ship.loop import ShipLoopAgent

    return ShipLoopAgent(find_repo_root())


def cmd_ship_discover(*, pr: int | None = None, as_json: bool = False) -> int:
    agent = _ship_agent()
    state = agent.discover(pr_number=pr)
    if as_json:
        print(json.dumps(state.to_dict(), indent=2))
        return 0
    print(f"Ship discover — branch={state.branch} pr={state.pr_number}")
    open_issues = state.open_issues()
    print(f"Open issues: {len(open_issues)}")
    for issue in state.issues:
        print(f"  [{issue.status.value}] {issue.id}: {issue.title}")
        if issue.fix_hint:
            print(f"           hint: {issue.fix_hint}")
    return 0


def cmd_ship_status(*, as_json: bool = False) -> int:
    agent = _ship_agent()
    status = agent.status()
    if as_json:
        print(json.dumps(status, indent=2))
        return 0
    print(f"Branch: {status.get('branch')}  PR: {status.get('pr_number')}")
    print(f"Open: {status.get('open_count')}  ready_for_merge={status.get('ready_for_merge')}")
    print(f"Can mark ready: {status.get('can_mark_ready')} — {status.get('ready_message')}")
    for issue in status.get("issues") or []:
        print(f"  [{issue['status']}] {issue['id']}: {issue['title']}")
    return 0


def cmd_ship_fixed(issue_id: str, *, note: str = "") -> int:
    agent = _ship_agent()
    state = agent.mark_fixed(issue_id, note=note)
    print(f"Marked fixed: {issue_id}")
    print(f"Open remaining: {len(state.open_issues())}")
    return 0


def cmd_ship_attempt(issue_id: str, *, blocked: bool = False, detail: str = "") -> int:
    agent = _ship_agent()
    state = agent.mark_attempt(issue_id, blocked=blocked, detail=detail)
    for issue in state.issues:
        if issue.id == issue_id:
            print(f"{issue_id}: attempts={issue.attempts} status={issue.status.value}")
            break
    return 0


def cmd_ship_proofread(*, as_json: bool = False) -> int:
    agent = _ship_agent()
    report = agent.proofread()
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Proofread: {'PASS' if report.ok else 'FAIL'}")
        print(f"  ruff={report.ruff_ok}  pytest={report.pytest_ok}")
        for note in report.notes:
            print(f"  · {note}")
    return 0 if report.ok else 1


def cmd_ship_ready(*, as_json: bool = False) -> int:
    agent = _ship_agent()
    try:
        state = agent.mark_ready()
    except RuntimeError as exc:
        print(f"Not ready: {exc}", file=sys.stderr)
        return 1
    payload = {
        "ready_for_merge": state.ready_for_merge,
        "branch": state.branch,
        "pr_number": state.pr_number,
        "message": (
            "Ship gates passed — mark PR ready for review; "
            "human merges (no auto-merge)."
        ),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print("READY FOR HUMAN MERGE")
        print(payload["message"])
        print(f"Branch: {state.branch}  PR: {state.pr_number}")
    return 0


def cmd_ship_next(*, as_json: bool = False) -> int:
    agent = _ship_agent()
    issue = agent.next_issue()
    if issue is None:
        if as_json:
            print(json.dumps({"next": None}))
        else:
            print("No open issues — run: aoa ship proofread && aoa ship ready")
        return 0
    if as_json:
        print(json.dumps({"next": issue.to_dict()}, indent=2))
    else:
        print(f"Next: {issue.id} — {issue.title}")
        print(f"Kind: {issue.kind.value}")
        if issue.fix_hint:
            print(f"Hint: {issue.fix_hint}")
        if issue.detail:
            print(f"Detail: {issue.detail[:400]}")
    return 0


def cmd_attl_run(
    cfg: Config,
    *,
    dry_run: bool = False,
    report: bool = False,
    as_json: bool = False,
) -> int:
    orch = _attl_orchestrator(cfg)
    # None → live Bob audit inside mesh; critical-only Kai
    result = orch.run(dry_run=dry_run, report=report, bob_can_proceed=None)
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        print(f"ATTL mesh — outcome: {result.outcome}")
        print(f"Mode: {result.mode}  dry_run={result.dry_run}")
        gate = result.gate or {}
        print(f"Gate: {gate.get('action')} — {gate.get('reason', '')}")
        if result.selected_task:
            print(
                f"Selected: {result.selected_task.get('id')} — "
                f"{result.selected_task.get('title')}"
            )
        if result.worktree:
            print(f"Worktree: {result.worktree.get('path')} ok={result.worktree.get('ok')}")
        print(f"Kai: {result.kai.get('verdict')} engaged={result.kai.get('engaged')}")
        for note in result.notes:
            print(f"  · {note}")
        print(f"Capture: {result.capture}")
    if result.outcome == "paused":
        return 2
    if result.outcome == "critical-report":
        return 2
    return 0


def cmd_attl_report(cfg: Config, *, as_json: bool = False) -> int:
    return cmd_attl_run(cfg, dry_run=False, report=True, as_json=as_json)


def _integrity_squad(cfg: Config):
    from aoa.config import data_dir_for
    from aoa.integrity import IntegritySquad

    return IntegritySquad(
        repo_root=Path.cwd(),
        data_dir=data_dir_for(cfg.env) / "integrity",
    )


def cmd_integrity_status(cfg: Config, *, as_json: bool = False) -> int:
    squad = _integrity_squad(cfg)
    status = squad.status()
    if as_json:
        print(json.dumps(status, indent=2))
        return 0
    print(f"Unit: {status['unit']}  roster={status['roster_size']}")
    print(f"Paused: {status['paused']}  mode={status['mode']}")
    print(f"Pending proposals: {status['pending_proposals']}")
    brain = status.get("brain") or {}
    print(
        "Brain: "
        f"members={brain.get('members')} algos={brain.get('algorithms')} "
        f"required_ok={brain.get('required_ok')}"
    )
    print(f"Queue: {status['queue_path']}")
    return 0


def cmd_integrity_roster(cfg: Config, *, as_json: bool = False) -> int:
    squad = _integrity_squad(cfg)
    rows = squad.roster()
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    print("Integrity Ten — cohesive integrity mesh")
    for i, row in enumerate(rows, start=1):
        print(f"  {i:2d}. {row['name']:<8} — {row['role']} [{row['domain']}]")
    return 0


def cmd_integrity_run(
    cfg: Config,
    *,
    dry_run: bool = False,
    notify: bool = True,
    as_json: bool = False,
) -> int:
    squad = _integrity_squad(cfg)
    result = squad.run(dry_run=dry_run, notify=notify)
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.outcome != "paused" else 2
    print(f"Integrity Ten — outcome: {result.outcome}")
    print(f"Worst status: {result.worst_status}  ok={result.ok}")
    for note in result.notes:
        print(f"  · {note}")
    if result.proposal:
        print(f"Proposal: {result.proposal.get('id')} (awaiting user approve/reject)")
        print("  aoa integrity approve <id>   # implant corrective action")
        print("  aoa integrity reject <id>    # decline implant")
    if result.capture:
        print(f"Capture: {result.capture}")
    return 0 if not result.paused else 2


def cmd_integrity_watch(
    cfg: Config,
    *,
    interval: int = 300,
    iterations: int | None = None,
    dry_run: bool = False,
    notify: bool = True,
) -> int:
    squad = _integrity_squad(cfg)
    print(
        f"Integrity Ten watch — interval={interval}s "
        f"iterations={'∞' if iterations is None else iterations}"
    )
    # Finite iterations for CLI safety when None not intended; default one pass
    # unless user passes --iterations. Continuous when iterations is None.
    results = squad.watch(
        interval_seconds=interval,
        iterations=iterations,
        dry_run=dry_run,
        notify=notify,
    )
    for i, result in enumerate(results, start=1):
        print(f"[{i}] outcome={result.outcome} worst={result.worst_status}")
        if result.proposal:
            print(f"    proposal={result.proposal.get('id')}")
        if result.paused:
            return 2
    return 0


def cmd_integrity_approve(cfg: Config, proposal_id: str, *, note: str = "") -> int:
    squad = _integrity_squad(cfg)
    try:
        result = squad.approve(proposal_id, note=note)
    except (KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Approved and implanted: {proposal_id}")
    applied = result.get("applied") or {}
    if applied.get("capture"):
        print(f"Capture: {applied['capture']}")
    if applied.get("repair_hint_queued"):
        print("Reed handoff queued (draft PR only — never auto-merge).")
    return 0


def cmd_integrity_reject(cfg: Config, proposal_id: str, *, note: str = "") -> int:
    squad = _integrity_squad(cfg)
    try:
        squad.reject(proposal_id, note=note)
    except (KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Rejected (no implant): {proposal_id}")
    return 0


def cmd_tasks_list() -> int:
    from aoa.loop.prompts import format_prompt_list

    print(format_prompt_list())
    return 0


def cmd_tasks_automations() -> int:
    from aoa.loop.prompts import format_automations

    print(format_automations())
    return 0


def cmd_tasks_show(shortkey: str) -> int:
    from aoa.loop.prompts import get_prompt

    prompt = get_prompt(shortkey)
    if prompt is None:
        print(f"Unknown shortkey {shortkey!r}. Run: aoa tasks list", file=sys.stderr)
        return 1
    header = f"=== {prompt.key}: {prompt.title} ==="
    if prompt.automation:
        header += f"\nAutomation: {prompt.automation}"
    if prompt.cadence:
        header += f"\nCadence: {prompt.cadence}"
    print(header)
    print()
    print(prompt.body)
    return 0


def cmd_tasks_run(task: str) -> int:
    from aoa.loop.prompts import run_task

    result = run_task(task)
    print(f"Task: {result.task}")
    print(f"OK: {result.ok}")
    if result.gate_action:
        print(f"Gate: {result.gate_action}")
    print(f"Steps: {', '.join(result.steps_run) or '(none)'}")
    print(result.message)
    return result.exit_code


def cmd_tasks_chain_status(*, as_json: bool = False) -> int:
    import json

    from aoa.config import Config
    from aoa.loop.task_chain import chain_status

    cfg = Config.from_env(load_dotenv=False)
    report = chain_status(env=cfg.env)
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Backlog: {report['backlog']}")
        print(f"Chain state: {report['chain_state']}")
        print(f"Completed: {', '.join(report['completed']) or '(none)'}")
        print(f"Current: {report['current'] or '(none)'} — {report['current_title'] or ''}")
        if report["skipped_human"]:
            print(f"Skipped (human): {', '.join(report['skipped_human'])}")
        if report["alerts"]:
            print("Alerts:")
            for line in report["alerts"]:
                print(f"  - {line}")
    return 0


def cmd_tasks_chain_bootstrap() -> int:
    from aoa.config import Config
    from aoa.loop.task_chain import bootstrap_chain_from_state, chain_status

    cfg = Config.from_env(load_dotenv=False)
    bootstrap_chain_from_state(env=cfg.env)
    report = chain_status(env=cfg.env)
    print(f"Bootstrapped task chain for env={cfg.env}")
    print(f"Current: {report['current']} — {report['current_title']}")
    return 0


def cmd_tasks_chain_advance(*, completed: str) -> int:
    from aoa.config import Config
    from aoa.loop.task_chain import advance_chain, format_advance_result

    cfg = Config.from_env(load_dotenv=False)
    try:
        result = advance_chain(completed.strip(), env=cfg.env)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(format_advance_result(result))
    if result.action.value == "alert_human":
        print("\n*** HUMAN ACTION REQUIRED — automation paused ***", file=sys.stderr)
    return result.exit_code


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
    if cfg.is_live_broker and not cfg.dry_run:
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


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "aoa").exists():
            return parent
    return Path.cwd()


def cmd_setup_moomoo(cfg: Config) -> int:
    """Run the Moomoo OpenD setup helper script."""
    script = _repo_root() / "scripts" / "setup_moomoo_auth.sh"
    if not script.is_file():
        print(f"Setup script not found: {script}", file=sys.stderr)
        return 1
    print("Running Moomoo setup helper…")
    print(f"  Broker: {cfg.broker} | OpenD: {cfg.moomoo_opend_host}:{cfg.moomoo_opend_port}")
    print("  Skills: .cursor/skills/moomooapi + install-moomoo-opend (official OpenD pack)")
    print("  Install OpenD via agent skill `/install-moomoo-opend` or scripts/install_moomoo_opend_*.sh")
    result = subprocess.run(["bash", str(script)], cwd=_repo_root(), check=False)
    return int(result.returncode)


def cmd_setup_mac(_cfg: Config) -> int:
    """Run the macOS bootstrap script (Python 3.10+, venv, pip install)."""
    script = _repo_root() / "scripts" / "setup_mac.sh"
    if not script.is_file():
        print(f"Setup script not found: {script}", file=sys.stderr)
        return 1
    print("Running macOS bootstrap (Python 3.10+, venv, pip install)…")
    result = subprocess.run(["bash", str(script)], cwd=_repo_root(), check=False)
    return int(result.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aoa", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Validate configuration & connectivity.")
    doctor.add_argument(
        "--offline",
        action="store_true",
        help="Validate config only; skip live broker and LLM checks.",
    )
    setup = sub.add_parser("setup", help="One-time broker and environment setup helpers.")
    setup_sub = setup.add_subparsers(dest="setup_command", required=True)
    setup_sub.add_parser(
        "moomoo",
        help="Install checks for Moomoo OpenD + moomoo-api (runs scripts/setup_moomoo_auth.sh).",
    )
    setup_sub.add_parser(
        "mac",
        help="macOS bootstrap: Python 3.10+, venv, pip install (runs scripts/setup_mac.sh).",
    )
    sub.add_parser("status", help="Show account, positions, and market clock.")
    sub.add_parser("run", help="Run a single team-coordinated swarm cycle.")
    lp = sub.add_parser("loop", help="Run team cycles continuously, or generate a user brief.")
    lp_sub = lp.add_subparsers(dest="loop_command", required=False)
    lp_brief = lp_sub.add_parser(
        "brief",
        help="Loop-aware user brief (Alex + STATE.md + repair queue).",
    )
    lp_brief.add_argument(
        "--push",
        action="store_true",
        help="Deliver the brief to your iPhone if a channel is configured.",
    )
    lp_brief.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
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

    hft = sub.add_parser(
        "hft",
        help="Offline HFT/L2 backtest via optional hftbacktest (never live).",
    )
    hft_sub = hft.add_subparsers(dest="hft_command", required=True)
    hft_status = hft_sub.add_parser("status", help="Show hftbacktest + orderbook lane status.")
    hft_status.add_argument("--json", action="store_true", help="Emit JSON.")
    hft_smoke = hft_sub.add_parser(
        "smoke", help="Run a synthetic L2 depth smoke backtest (no orders)."
    )
    hft_smoke.add_argument("--events", type=int, default=400, help="Synthetic depth events.")
    hft_smoke.add_argument("--steps", type=int, default=20, help="elapse() steps to advance.")
    hft_smoke.add_argument("--seed", type=int, default=1, help="RNG seed for the tape.")
    hft_smoke.add_argument("--json", action="store_true", help="Emit JSON.")
    hft_book = hft_sub.add_parser(
        "book-smoke",
        help="Smoke the vendored HFT-Orderbook LOB (add/update/cancel; offline).",
    )
    hft_book.add_argument("--json", action="store_true", help="Emit JSON.")
    hft_run = hft_sub.add_parser(
        "run",
        help="Probe an on-disk hftbacktest feed (advance time; no order submission).",
    )
    hft_run.add_argument("data", help="Path to hftbacktest NPZ/feed file.")
    hft_run.add_argument("--tick-size", type=float, required=True, help="Instrument tick size.")
    hft_run.add_argument("--lot-size", type=float, required=True, help="Instrument lot size.")
    hft_run.add_argument("--steps", type=int, default=20, help="elapse() steps to advance.")
    hft_run.add_argument(
        "--step-ns", type=int, default=50_000_000, help="Nanoseconds per elapse step."
    )
    hft_run.add_argument("--json", action="store_true", help="Emit JSON.")

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

    av = sub.add_parser(
        "avellaneda",
        help="Offline Avellaneda–Stoikov market-making research (never live).",
    )
    av_sub = av.add_subparsers(dest="avellaneda_command", required=True)
    av_status = av_sub.add_parser("status", help="Show Avellaneda–Stoikov research-lane status.")
    av_status.add_argument("--json", action="store_true", help="Emit JSON.")
    av_smoke = av_sub.add_parser(
        "smoke",
        help="Check reservation quotes + a short Monte-Carlo ensemble.",
    )
    av_smoke.add_argument("--steps", type=int, default=200, help="Steps per path.")
    av_smoke.add_argument("--sims", type=int, default=20, help="Ensemble size for smoke.")
    av_smoke.add_argument("--seed", type=int, default=1, help="RNG seed.")
    av_smoke.add_argument("--json", action="store_true", help="Emit JSON.")
    av_sim = av_sub.add_parser("simulate", help="Run one AS path or an ensemble.")
    av_sim.add_argument("--steps", type=int, default=200, help="Steps per path.")
    av_sim.add_argument("--seed", type=int, default=1, help="RNG seed.")
    av_sim.add_argument(
        "--ensemble",
        action="store_true",
        help="Average PnL over --sims independent seeds.",
    )
    av_sim.add_argument("--sims", type=int, default=50, help="Ensemble size when --ensemble.")
    av_sim.add_argument(
        "--unlimited",
        action="store_true",
        help="Use unlimited-horizon quotes instead of finite T.",
    )
    av_sim.add_argument("--json", action="store_true", help="Emit JSON.")

    vh = sub.add_parser(
        "visualhft",
        help="Offline VisualHFT microstructure studies (never live).",
    )
    vh_sub = vh.add_subparsers(dest="visualhft_command", required=True)
    vh_status = vh_sub.add_parser("status", help="Show VisualHFT research-lane status.")
    vh_status.add_argument("--json", action="store_true", help="Emit JSON.")
    vh_smoke = vh_sub.add_parser(
        "smoke",
        help="Run LOB imbalance / VPIN / OTR on a synthetic tape.",
    )
    vh_smoke.add_argument(
        "--trades",
        type=int,
        default=200,
        help="Synthetic trade count (minimum 20 so VPIN can complete a bucket).",
    )
    vh_smoke.add_argument("--seed", type=int, default=1, help="RNG seed for the tape.")
    vh_smoke.add_argument("--json", action="store_true", help="Emit JSON.")
    vh_studies = vh_sub.add_parser("studies", help="List VisualHFT studies and port status.")
    vh_studies.add_argument("--json", action="store_true", help="Emit JSON.")
    vh_studies.add_argument(
        "--ported-only",
        action="store_true",
        help="Only list studies with a Python port.",
    )

    ms = sub.add_parser(
        "microstructure",
        help="Mesh status for all offline HFT/LOB research lanes (never live).",
    )
    ms_sub = ms.add_subparsers(dest="microstructure_command", required=True)
    ms_status = ms_sub.add_parser("status", help="Show aggregated lane availability.")
    ms_status.add_argument("--json", action="store_true", help="Emit JSON.")

    ws = sub.add_parser(
        "workspaces",
        help="Companion workspace mesh (OpenStock, QM, VisualHFT, hftbacktest).",
    )
    ws_sub = ws.add_subparsers(dest="workspaces_command", required=True)
    ws_status = ws_sub.add_parser(
        "status",
        help="Show sibling workspace link/path status (never live).",
    )
    ws_status.add_argument("--json", action="store_true", help="Emit JSON.")
    ws_sub.add_parser(
        "setup",
        help="Clone missing companions (OpenStock/QM/VisualHFT/…) and refresh AOA.code-workspace.",
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
    wl_up = wl_sub.add_parser(
        "upgrade",
        help="Dependency upgrade pipeline: verify → pip upgrade → reverify.",
    )
    wl_up.add_argument(
        "--dry-run",
        action="store_true",
        help="Run baseline verify only; skip pip upgrade.",
    )

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
    rp_gate = rp_sub.add_parser(
        "gate",
        help="Preflight for Tier 1/2 automations (budget, pause flag, fixable queue).",
    )
    rp_gate.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    rp_gate.add_argument(
        "--for",
        dest="gate_mode",
        choices=("full", "triage", "repair"),
        default="full",
        help="Gate mode: triage (Automation A), repair (Automation B), or full.",
    )
    rp_wt = rp_sub.add_parser("worktree", help="Create an isolated git worktree for a fix.")
    rp_wt.add_argument("--item-id", default="", help="Repair item id (optional).")

    vp = sub.add_parser("vault", help="Schema-driven vault property sync.")
    vp_sub = vp.add_subparsers(dest="vault_command", required=True)
    vp_sync = vp_sub.add_parser("sync", help="Analyze and update all vault properties.")
    vp_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing (also forced when L1-only).",
    )
    vp_sync.add_argument("--json", action="store_true", help="Emit JSON result.")
    vp_status = vp_sub.add_parser("status", help="Report stale vault properties.")
    vp_status.add_argument("--json", action="store_true", help="Emit JSON report.")

    st = sub.add_parser(
        "study",
        help="Study cortex — learn DE/physics/econ bridges, use in swarm, export for sLM/LoRA.",
    )
    st_sub = st.add_subparsers(dest="study_command", required=True)
    st_status = st_sub.add_parser("status", help="Mastery overview by field.")
    st_status.add_argument("--json", action="store_true", help="Emit JSON.")
    st_drill = st_sub.add_parser("drill", help="Next spaced drills (prompts only by default).")
    st_drill.add_argument("-n", type=int, default=3, help="Number of cards.")
    st_drill.add_argument(
        "--field",
        default="",
        help="Filter: de | physics | econ | bridge",
    )
    st_drill.add_argument(
        "--reveal",
        action="store_true",
        help="Include proof sketches (open-book mode).",
    )
    st_drill.add_argument("--json", action="store_true", help="Emit JSON.")
    st_show = st_sub.add_parser("show", help="Reveal a card (statement + proof + mesh).")
    st_show.add_argument("card_id", help="Card id, e.g. bridge-bs-heat")
    st_show.add_argument("--json", action="store_true", help="Emit JSON.")
    st_grade = st_sub.add_parser("grade", help="Record drill result (ok|miss).")
    st_grade.add_argument("card_id", help="Card id")
    st_grade.add_argument("result", help="ok or miss")
    st_grade.add_argument("--note", default="", help="Optional lesson note")
    st_usage = st_sub.add_parser("usage", help="Print mastered meshes for swarm injection.")
    st_usage.add_argument("--json", action="store_true", help="Emit JSON.")
    st_export = st_sub.add_parser(
        "export",
        help="Export JSONL corpus for LoRA/sLM distillation.",
    )
    st_export.add_argument(
        "--out",
        default="",
        help="Output path (default: data/{env}/study/corpus.jsonl)",
    )
    st_export.add_argument(
        "--only-mastered",
        action="store_true",
        help="Export only cards with mastery ≥ 0.6",
    )
    st_sync = st_sub.add_parser("sync", help="Write vault/study notes from curriculum + mastery.")
    st_sync.add_argument("--json", action="store_true", help="Emit JSON.")

    hf = sub.add_parser(
        "hftish",
        help="example-hftish order-book imbalance research lane (no orders).",
    )
    hf_sub = hf.add_subparsers(dest="hftish_command", required=True)
    hf_status = hf_sub.add_parser("status", help="Show companion wiring + consumers.")
    hf_status.add_argument("--json", action="store_true", help="Emit JSON.")
    hf_smoke = hf_sub.add_parser(
        "smoke",
        help="Offline synthetic level-change / imbalance / follow check.",
    )
    hf_smoke.add_argument("--seed", type=int, default=7, help="Reserved for future RNG.")
    hf_smoke.add_argument("--json", action="store_true", help="Emit JSON.")

    tk = sub.add_parser(
        "tasks",
        help="Loop prompt shortkeys (L1, L2, …) and deterministic task runners.",
    )
    tk_sub = tk.add_subparsers(dest="tasks_command", required=True)
    tk_sub.add_parser("list", help="List prompt shortkeys and task loops.")
    tk_sub.add_parser(
        "automations",
        help="Print ready-to-create Cursor automation specs (A/B/C).",
    )
    tk_show = tk_sub.add_parser("show", help="Print a copy-paste prompt by shortkey.")
    tk_show.add_argument(
        "shortkey",
        help="Prompt key, e.g. L1, L2, GATE-A, SETUP (see: aoa tasks list).",
    )
    tk_run = tk_sub.add_parser(
        "run",
        help="Run a deterministic task loop (tier1, tier1-check, tier2-check, verify).",
    )
    tk_run.add_argument("task", help="Task name from loop-prompts.yaml.")
    tk_chain = tk_sub.add_parser(
        "chain",
        help="Upgrade backlog task chain — auto-queue next L2 item.",
    )
    tk_chain_sub = tk_chain.add_subparsers(dest="chain_command", required=True)
    tk_chain_status = tk_chain_sub.add_parser("status", help="Show chain state.")
    tk_chain_status.add_argument("--json", action="store_true", help="Emit JSON.")
    tk_chain_sub.add_parser("bootstrap", help="Seed chain from docs/upgrade-backlog.json.")
    tk_chain_adv = tk_chain_sub.add_parser(
        "advance",
        help="Mark item complete and queue next automatable task in STATE.md.",
    )
    tk_chain_adv.add_argument(
        "--complete",
        required=True,
        metavar="ID",
        help="Backlog item id, e.g. upg-007",
    )

    at = sub.add_parser(
        "attl",
        help="Agentic Task-Team Loop — auto-12, brain mesh, critical-only review.",
    )
    at_sub = at.add_subparsers(dest="attl_command", required=True)
    at_sub.add_parser("init", help="Ensure brain/ workspace + ATTL config (auto-12).")
    at_status = at_sub.add_parser("status", help="Show ATTL mode, roster, mesh stats.")
    at_status.add_argument("--json", action="store_true", help="Emit JSON.")
    at_roster = at_sub.add_parser("roster", help="Print the 12-member meshed team.")
    at_roster.add_argument("--json", action="store_true", help="Emit JSON.")
    at_sub.add_parser("propose", help="Reed: auto-propose tasks from repair/backlog.")
    at_run = at_sub.add_parser("run", help="One ATTL auto cycle (Kai only if critical).")
    at_run.add_argument("--dry-run", action="store_true", help="No side-effect notes beyond capture.")
    at_run.add_argument("--report", action="store_true", help="Force Kai report path.")
    at_run.add_argument("--json", action="store_true", help="Emit JSON.")
    at_report = at_sub.add_parser("report", help="Force critical report via Kai/Aaron path.")
    at_report.add_argument("--json", action="store_true", help="Emit JSON.")
    at_brain = at_sub.add_parser("brain", help="Second-brain workspace ops.")
    at_brain_sub = at_brain.add_subparsers(dest="brain_command", required=True)
    at_brain_sync = at_brain_sub.add_parser("sync", help="Nova: refresh mesh + capture.")
    at_brain_sync.add_argument("--json", action="store_true", help="Emit JSON.")

    integ = sub.add_parser(
        "integrity",
        help="Integrity Ten — continuous code/workspace/neural/mesh checks.",
    )
    integ_sub = integ.add_subparsers(dest="integrity_command", required=True)
    integ_status = integ_sub.add_parser(
        "status", help="Show Integrity Ten status and pending proposals."
    )
    integ_status.add_argument("--json", action="store_true", help="Emit JSON.")
    integ_roster = integ_sub.add_parser(
        "roster", help="Print the 10-member integrity mesh."
    )
    integ_roster.add_argument("--json", action="store_true", help="Emit JSON.")
    integ_run = integ_sub.add_parser(
        "run",
        help="One integrity cycle; notify user if corrective action needs approval.",
    )
    integ_run.add_argument(
        "--dry-run", action="store_true", help="Check only; do not queue proposals."
    )
    integ_run.add_argument(
        "--no-notify",
        action="store_true",
        help="Skip iPhone/push dispatch (still writes proposal + capture).",
    )
    integ_run.add_argument("--json", action="store_true", help="Emit JSON.")
    integ_watch = integ_sub.add_parser(
        "watch",
        help="Continuously run Integrity Ten cycles (Ctrl-C to stop).",
    )
    integ_watch.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between cycles (default 300).",
    )
    integ_watch.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Stop after N cycles (default: run until pause/Ctrl-C).",
    )
    integ_watch.add_argument("--dry-run", action="store_true", help="Check only.")
    integ_watch.add_argument(
        "--no-notify", action="store_true", help="Skip push dispatch."
    )
    integ_approve = integ_sub.add_parser(
        "approve",
        help="User approves implant of a corrective proposal.",
    )
    integ_approve.add_argument("proposal_id", help="Proposal id from integrity run.")
    integ_approve.add_argument("--note", default="", help="Optional approval note.")
    integ_reject = integ_sub.add_parser(
        "reject",
        help="User rejects implant of a corrective proposal.",
    )
    integ_reject.add_argument("proposal_id", help="Proposal id from integrity run.")
    integ_reject.add_argument("--note", default="", help="Optional rejection note.")

    ship = sub.add_parser(
        "ship",
        help="Ship-ready task loop — discover issues, proofread, mark ready (no auto-merge).",
    )
    ship_sub = ship.add_subparsers(dest="ship_command", required=True)
    ship_disc = ship_sub.add_parser("discover", help="Scan branch and seed the ship issue queue.")
    ship_disc.add_argument("--pr", type=int, default=None, help="PR number to associate.")
    ship_disc.add_argument("--json", action="store_true", help="Emit JSON.")
    ship_status = ship_sub.add_parser("status", help="Show ship-loop queue and readiness.")
    ship_status.add_argument("--json", action="store_true", help="Emit JSON.")
    ship_next = ship_sub.add_parser("next", help="Print the next open ship issue.")
    ship_next.add_argument("--json", action="store_true", help="Emit JSON.")
    ship_fixed = ship_sub.add_parser("fixed", help="Mark an issue fixed.")
    ship_fixed.add_argument("issue_id", help="Issue id from ship discover/status.")
    ship_fixed.add_argument("--note", default="", help="Optional note.")
    ship_attempt = ship_sub.add_parser("attempt", help="Record a fix attempt (blocks after 3).")
    ship_attempt.add_argument("issue_id", help="Issue id.")
    ship_attempt.add_argument("--blocked", action="store_true", help="Force blocked status.")
    ship_attempt.add_argument("--detail", default="", help="Attempt detail.")
    ship_proof = ship_sub.add_parser("proofread", help="Independent ruff+pytest proofread gate.")
    ship_proof.add_argument("--json", action="store_true", help="Emit JSON.")
    ship_ready = ship_sub.add_parser(
        "ready",
        help="Mark ready for human merge after all gates pass (never auto-merges).",
    )
    ship_ready.add_argument("--json", action="store_true", help="Emit JSON.")

    args = parser.parse_args(argv)

    # Offline research lanes — no .env template and no Config/broker side effects.
    if args.command == "visualhft":
        if args.visualhft_command == "status":
            return cmd_visualhft_status(as_json=getattr(args, "json", False))
        if args.visualhft_command == "smoke":
            return cmd_visualhft_smoke(
                n_trades=getattr(args, "trades", 200),
                seed=getattr(args, "seed", 1),
                as_json=getattr(args, "json", False),
            )
        if args.visualhft_command == "studies":
            return cmd_visualhft_studies(
                as_json=getattr(args, "json", False),
                ported_only=getattr(args, "ported_only", False),
            )
        return 2

    if args.command == "workspaces":
        if args.workspaces_command == "status":
            return cmd_workspaces_status(as_json=getattr(args, "json", False))
        if args.workspaces_command == "setup":
            return cmd_workspaces_setup()
        return 2

    # Offline research lane — no .env template and no Config/broker side effects.
    if args.command == "hftish":
        if args.hftish_command == "status":
            return cmd_hftish_status(as_json=getattr(args, "json", False))
        if args.hftish_command == "smoke":
            return cmd_hftish_smoke(
                seed=getattr(args, "seed", 7),
                as_json=getattr(args, "json", False),
            )
        return 2

    if args.command == "hft":
        if args.hft_command == "status":
            return cmd_hft_status(as_json=getattr(args, "json", False))
        if args.hft_command == "smoke":
            return cmd_hft_smoke(
                n_events=getattr(args, "events", 400),
                steps=getattr(args, "steps", 20),
                seed=getattr(args, "seed", 1),
                as_json=getattr(args, "json", False),
            )
        if args.hft_command == "book-smoke":
            return cmd_hft_book_smoke(as_json=getattr(args, "json", False))
        if args.hft_command == "run":
            return cmd_hft_run(
                data=args.data,
                tick_size=args.tick_size,
                lot_size=args.lot_size,
                steps=getattr(args, "steps", 20),
                step_ns=getattr(args, "step_ns", 50_000_000),
                as_json=getattr(args, "json", False),
            )
        return 2
    if args.command == "avellaneda":
        if args.avellaneda_command == "status":
            return cmd_avellaneda_status(as_json=getattr(args, "json", False))
        if args.avellaneda_command == "smoke":
            return cmd_avellaneda_smoke(
                n_steps=getattr(args, "steps", 200),
                n_sims=getattr(args, "sims", 20),
                seed=getattr(args, "seed", 1),
                as_json=getattr(args, "json", False),
            )
        if args.avellaneda_command == "simulate":
            return cmd_avellaneda_simulate(
                n_steps=getattr(args, "steps", 200),
                seed=getattr(args, "seed", 1),
                ensemble=getattr(args, "ensemble", False),
                n_sims=getattr(args, "sims", 50),
                unlimited=getattr(args, "unlimited", False),
                as_json=getattr(args, "json", False),
            )
        return 2
    if args.command == "microstructure":
        if args.microstructure_command == "status":
            return cmd_microstructure_status(as_json=getattr(args, "json", False))
        return 2

    _ensure_env_template()
    cfg = Config.from_env()

    try:
        if args.command == "bars":
            return cmd_bars(cfg, args.symbols, timeframe=args.timeframe, limit=args.limit)
        if args.command == "doctor":
            return cmd_doctor(cfg, offline=getattr(args, "offline", False))
        if args.command == "setup":
            if args.setup_command == "moomoo":
                return cmd_setup_moomoo(cfg)
            if args.setup_command == "mac":
                return cmd_setup_mac(cfg)
        if args.command == "status":
            return cmd_status(cfg)
        if args.command == "run":
            return cmd_run(cfg)
        if args.command == "loop":
            if getattr(args, "loop_command", None) == "brief":
                return cmd_loop_brief(
                    cfg, push=args.push, as_json=getattr(args, "json", False)
                )
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
            if args.workloop_command == "upgrade":
                return cmd_workloop_upgrade(
                    cfg, dry_run=getattr(args, "dry_run", False)
                )
        if args.command == "repair":
            if args.repair_command == "triage":
                return cmd_repair_triage(cfg, no_sync=getattr(args, "no_sync", False))
            if args.repair_command == "queue":
                return cmd_repair_queue(cfg)
            if args.repair_command == "gate":
                return cmd_repair_gate(
                    cfg,
                    as_json=getattr(args, "json", False),
                    mode=getattr(args, "gate_mode", "full"),
                )
            if args.repair_command == "worktree":
                return cmd_repair_worktree(cfg, item_id=getattr(args, "item_id", ""))
        if args.command == "vault":
            if args.vault_command == "sync":
                return cmd_vault_sync(
                    cfg,
                    dry_run=getattr(args, "dry_run", False),
                    as_json=getattr(args, "json", False),
                )
            if args.vault_command == "status":
                return cmd_vault_status(cfg, as_json=getattr(args, "json", False))
        if args.command == "study":
            if args.study_command == "status":
                return cmd_study_status(cfg, as_json=getattr(args, "json", False))
            if args.study_command == "drill":
                return cmd_study_drill(
                    cfg,
                    n=getattr(args, "n", 3),
                    field=getattr(args, "field", "") or "",
                    reveal=getattr(args, "reveal", False),
                    as_json=getattr(args, "json", False),
                )
            if args.study_command == "show":
                return cmd_study_show(
                    cfg, args.card_id, as_json=getattr(args, "json", False)
                )
            if args.study_command == "grade":
                return cmd_study_grade(
                    cfg, args.card_id, args.result, note=getattr(args, "note", "")
                )
            if args.study_command == "usage":
                return cmd_study_usage(cfg, as_json=getattr(args, "json", False))
            if args.study_command == "export":
                return cmd_study_export(
                    cfg,
                    out=getattr(args, "out", "") or "",
                    only_mastered=getattr(args, "only_mastered", False),
                )
            if args.study_command == "sync":
                return cmd_study_sync(cfg, as_json=getattr(args, "json", False))
        if args.command == "tasks":
            if args.tasks_command == "automations":
                return cmd_tasks_automations()
            if args.tasks_command == "list":
                return cmd_tasks_list()
            if args.tasks_command == "show":
                return cmd_tasks_show(args.shortkey)
            if args.tasks_command == "run":
                return cmd_tasks_run(args.task)
            if args.tasks_command == "chain":
                if args.chain_command == "status":
                    return cmd_tasks_chain_status(as_json=getattr(args, "json", False))
                if args.chain_command == "bootstrap":
                    return cmd_tasks_chain_bootstrap()
                if args.chain_command == "advance":
                    return cmd_tasks_chain_advance(completed=args.complete)
        if args.command == "attl":
            if args.attl_command == "init":
                return cmd_attl_init(cfg)
            if args.attl_command == "status":
                return cmd_attl_status(cfg, as_json=getattr(args, "json", False))
            if args.attl_command == "roster":
                return cmd_attl_roster(cfg, as_json=getattr(args, "json", False))
            if args.attl_command == "propose":
                return cmd_attl_propose(cfg)
            if args.attl_command == "run":
                return cmd_attl_run(
                    cfg,
                    dry_run=getattr(args, "dry_run", False),
                    report=getattr(args, "report", False),
                    as_json=getattr(args, "json", False),
                )
            if args.attl_command == "report":
                return cmd_attl_report(cfg, as_json=getattr(args, "json", False))
            if args.attl_command == "brain":
                if args.brain_command == "sync":
                    return cmd_attl_brain_sync(cfg, as_json=getattr(args, "json", False))
        if args.command == "integrity":
            if args.integrity_command == "status":
                return cmd_integrity_status(cfg, as_json=getattr(args, "json", False))
            if args.integrity_command == "roster":
                return cmd_integrity_roster(cfg, as_json=getattr(args, "json", False))
            if args.integrity_command == "run":
                return cmd_integrity_run(
                    cfg,
                    dry_run=getattr(args, "dry_run", False),
                    notify=not getattr(args, "no_notify", False),
                    as_json=getattr(args, "json", False),
                )
            if args.integrity_command == "watch":
                return cmd_integrity_watch(
                    cfg,
                    interval=getattr(args, "interval", 300),
                    iterations=getattr(args, "iterations", None),
                    dry_run=getattr(args, "dry_run", False),
                    notify=not getattr(args, "no_notify", False),
                )
            if args.integrity_command == "approve":
                return cmd_integrity_approve(
                    cfg, args.proposal_id, note=getattr(args, "note", "") or ""
                )
            if args.integrity_command == "reject":
                return cmd_integrity_reject(
                    cfg, args.proposal_id, note=getattr(args, "note", "") or ""
                )
        if args.command == "ship":
            if args.ship_command == "discover":
                return cmd_ship_discover(
                    pr=getattr(args, "pr", None),
                    as_json=getattr(args, "json", False),
                )
            if args.ship_command == "status":
                return cmd_ship_status(as_json=getattr(args, "json", False))
            if args.ship_command == "next":
                return cmd_ship_next(as_json=getattr(args, "json", False))
            if args.ship_command == "fixed":
                return cmd_ship_fixed(args.issue_id, note=getattr(args, "note", "") or "")
            if args.ship_command == "attempt":
                return cmd_ship_attempt(
                    args.issue_id,
                    blocked=getattr(args, "blocked", False),
                    detail=getattr(args, "detail", "") or "",
                )
            if args.ship_command == "proofread":
                return cmd_ship_proofread(as_json=getattr(args, "json", False))
            if args.ship_command == "ready":
                return cmd_ship_ready(as_json=getattr(args, "json", False))
    except (BrokerError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
