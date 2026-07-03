"""Command-line interface for the AOA Financial swarm.

Commands:
  aoa doctor    Validate configuration & connectivity.
  aoa status    Show account, positions, and market clock.
  aoa run       Run a single analysis→decision→execution cycle.
  aoa loop      Run cycles continuously on the configured cadence.
  aoa serve     Start the web dashboard and REST API.
  aoa journal      Print the tail of the decision/trade journal.
  aoa workloop     Run the autonomous discover→merge improvement loop.
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
from aoa.workloop.orchestrator import WorkloopOrchestrator, WorkloopResult
from aoa.workloop.scheduler import WorkloopScheduler, build_scheduler
from aoa.workloop.models import STAGE_ORDER


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
    if offline or cfg.is_test:
        label = "Offline mode" if offline else "Test environment"
        print(f"  ✓ {label} — skipping broker/LLM connectivity checks.")
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
    orch = build_orchestrator(cfg)
    if not orch.broker.is_market_open():
        print("Market is closed. Running analysis anyway (orders may queue/reject).")
    result = orch.run_cycle()
    _print_cycle(result)
    return _cycle_exit_code(result)


def cmd_loop(cfg: Config) -> int:
    orch = build_orchestrator(cfg)
    _print_environment(cfg)
    print(
        f"Starting continuous loop: cadence={cfg.cycle_seconds}s. Ctrl-C to stop."
    )
    try:
        while True:
            if orch.broker.is_market_open():
                result = orch.run_cycle()
                _print_cycle(result)
                if _cycle_exit_code(result):
                    print("Cycle finished with execution errors.", file=sys.stderr)
            else:
                print("Market closed — sleeping.")
            time.sleep(cfg.cycle_seconds)
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
        print(f"\nAwaiting approval from {approver}. Run: aoa workloop approve")


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
    sub.add_parser("run", help="Run a single swarm cycle.")
    sub.add_parser("loop", help="Run cycles continuously.")
    sub.add_parser("serve", help="Start the web dashboard and REST API.")
    jp = sub.add_parser("journal", help="Tail the decision/trade journal.")
    jp.add_argument("-n", type=int, default=20, help="Number of entries to show.")

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
    except (BrokerError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
