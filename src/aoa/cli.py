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
        data_feed=cfg.alpaca_data_feed,
        bar_adjustment=cfg.alpaca_bar_adjustment,
    )


def build_llm(cfg: Config) -> LLMClient:
    return LLMClient(cfg.anthropic_api_key, model=cfg.model, effort=cfg.effort)


def build_news(cfg: Config) -> NewsFeed:
    if not cfg.news_enabled or not cfg.has_brokerage_creds:
        return NullNewsFeed()
    return AlpacaNewsFeed(cfg.alpaca_key_id, cfg.alpaca_secret_key)


def build_orchestrator(cfg: Config) -> Orchestrator:
    return Orchestrator(
        cfg,
        build_broker(cfg),
        build_llm(cfg),
        Journal(cfg.journal_path),
        build_news(cfg),
    )


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
    if result.decision:
        print("\n=== Alan — decision brief ===")
        print(f"  {result.decision.summary} (confidence={result.decision.confidence:.2f})")
        for rec in result.decision.recommendations:
            print(
                f"  • {rec.get('symbol', '?'):<6} {rec.get('action', '?'):<18} "
                f"conv={rec.get('conviction', 0):.2f}  {rec.get('rationale', '')[:50]}"
            )
    if result.ceo:
        print("\n=== Aaron — CEO review ===")
        print(f"  {result.ceo.summary}")
    if result.halted:
        print(f"\nCycle halted: {result.halt_reason}")
    elif result.cycle:
        _print_cycle(result.cycle)


# --------------------------------------------------------------------- commands
def cmd_doctor(cfg: Config, *, offline: bool = False) -> int:
    print(f"AOA Financial — trading mode: {cfg.trading_mode.upper()}")
    problems = cfg.validate()
    if problems:
        print("Configuration problems:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("  ✓ Configuration looks complete.")
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
    team = build_team(cfg)
    if not team.broker.is_market_open():
        print("Market is closed. Running analysis anyway (orders may queue/reject).")
    result = team.run_cycle()
    _print_team(result)
    return 0


def cmd_loop(cfg: Config) -> int:
    team = build_team(cfg)
    print(
        f"Starting continuous loop (team mode): mode={cfg.trading_mode}, "
        f"cadence={cfg.cycle_seconds}s. Ctrl-C to stop."
    )
    try:
        while True:
            if team.broker.is_market_open():
                result = team.run_cycle()
                _print_team(result)
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
    if not health.can_proceed:
        _print_team(TeamCycleResult(health=health, halted=True, halt_reason=health.summary))
        return 1
    trends, algorithms, decision = team.run_team_brief()
    _print_team(
        TeamCycleResult(
            health=health,
            trends=trends,
            algorithms=algorithms,
            decision=decision,
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
    team_sub.add_parser("health", help="Run Bob's health and code-integrity checks.")
    team_sub.add_parser("brief", help="Run Tom→Julie→Alan brief without trading.")
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
        if args.command == "serve":
            return cmd_serve(cfg)
        if args.command == "journal":
            return cmd_journal(cfg, args.n)
        if args.command == "team":
            if args.team_command == "health":
                return cmd_team_health(cfg)
            if args.team_command == "brief":
                return cmd_team_brief(cfg)
    except (BrokerError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
