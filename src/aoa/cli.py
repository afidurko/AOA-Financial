"""Command-line interface for the AOA Financial swarm.

Commands:
  aoa doctor    Validate configuration & connectivity.
  aoa status    Show account, positions, and market clock.
  aoa run       Run a single analysis→decision→execution cycle.
  aoa loop      Run cycles continuously on the configured cadence.
  aoa serve     Start the web dashboard and REST API.
  aoa journal   Print the tail of the decision/trade journal.
"""

from __future__ import annotations

import argparse
import sys
import time

from aoa.brokerage.alpaca import AlpacaBroker
from aoa.brokerage.base import Broker, BrokerError
from aoa.config import Config
from aoa.data.news import AlpacaNewsFeed, NewsFeed, NullNewsFeed
from aoa.journal.store import Journal
from aoa.llm.client import LLMClient, LLMError
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


def build_orchestrator(cfg: Config) -> Orchestrator:
    return Orchestrator(
        cfg,
        build_broker(cfg),
        build_llm(cfg),
        Journal(cfg.journal_path),
        build_news(cfg),
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
    return 0


def cmd_status(cfg: Config) -> int:
    _print_environment(cfg)
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
    except (BrokerError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
