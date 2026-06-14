"""Command-line interface for the AOA Financial swarm.

Commands:
  aoa doctor    Validate configuration & connectivity.
  aoa status    Show account, positions, and market clock.
  aoa run       Run a single analysis→decision→execution cycle.
  aoa loop      Run cycles continuously on the configured cadence.
  aoa journal   Print the tail of the decision/trade journal.
  aoa report    Summarize activity (from the journal) and live P&L.
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
from aoa.reporting import position_pnl, summarize_journal
from aoa.state import StateStore
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


def cmd_journal(cfg: Config, n: int) -> int:
    entries = Journal().tail(n)
    if not entries:
        print("Journal is empty.")
        return 0
    for e in entries:
        print(f"{e.get('ts', '')}  {e.get('event', '')}")
    return 0


def cmd_report(cfg: Config) -> int:
    summary = summarize_journal(Journal().read_all())
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
    sub.add_parser("doctor", help="Validate configuration & connectivity.")
    sub.add_parser("status", help="Show account, positions, and market clock.")
    sub.add_parser("run", help="Run a single swarm cycle.")
    sub.add_parser("loop", help="Run cycles continuously.")
    jp = sub.add_parser("journal", help="Tail the decision/trade journal.")
    jp.add_argument("-n", type=int, default=20, help="Number of entries to show.")
    sub.add_parser("report", help="Summarize activity and live P&L.")

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
        if args.command == "report":
            return cmd_report(cfg)
    except (BrokerError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
