"""Property analyzers for vault sync."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.team.code_engineering import run_code_quality_audit

AnalyzerFn = Callable[["AnalyzerContext"], dict[str, Any]]


@dataclass
class AnalyzerContext:
    repo_root: Path
    vault_root: Path
    note_path: Path | None = None
    note_type: str = ""
    cycle_ctx: Any | None = None
    workloop_extracted: dict[str, Any] = field(default_factory=dict)
    run_verify: bool = False
    repair_path: Path | None = None


_ANALYZERS: dict[str, AnalyzerFn] = {}


def register(source: str, fn: AnalyzerFn) -> None:
    _ANALYZERS[source] = fn


def run_analyzer(source: str, ctx: AnalyzerContext) -> dict[str, Any]:
    fn = _ANALYZERS.get(source)
    if fn is None:
        return {}
    return fn(ctx)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _parse_state_md(state_path: Path) -> dict[str, Any]:
    if not state_path.is_file():
        return {
            "last_run": "",
            "high_priority_count": 0,
            "watch_count": 0,
            "l1_enabled": False,
            "l2_enabled": False,
        }
    text = state_path.read_text(encoding="utf-8")
    last_run = ""
    for line in text.splitlines():
        if line.startswith("Last run:"):
            last_run = line.replace("Last run:", "").strip()
            break
    high_count = _count_section_bullets(text, "## High Priority")
    watch_count = _count_section_bullets(text, "## Watch List")
    loop_auto = _extract_section(text, "## Loop automation")
    l1 = "L1:" in loop_auto and "enabled" in loop_auto.lower()
    l2 = "L2: enabled" in loop_auto or "L2:** enabled" in loop_auto
    return {
        "last_run": last_run,
        "high_priority_count": high_count,
        "watch_count": watch_count,
        "l1_enabled": l1,
        "l2_enabled": l2,
    }


def _count_section_bullets(text: str, header: str) -> int:
    section = _extract_section(text, header)
    count = 0
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- **") and "_(none" not in stripped:
            count += 1
    return count


def _extract_section(text: str, header: str) -> str:
    lines = text.splitlines()
    start = None
    header_prefix = header.strip()
    for i, line in enumerate(lines):
        if line.strip() == header_prefix or line.strip().startswith(header_prefix):
            start = i + 1
            break
    if start is None:
        return ""
    out: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


def _analyze_loop_engineering(ctx: AnalyzerContext) -> dict[str, Any]:
    from aoa.repair.store import RepairStore

    state = _parse_state_md(ctx.repo_root / "STATE.md")
    queue_size = 0
    if ctx.repair_path is not None:
        store = RepairStore(ctx.repair_path)
        queue_size = len(store.load_queue())
    else:
        data_root = ctx.repo_root / "data"
        if data_root.is_dir():
            for repair_dir in sorted(data_root.glob("*/repair")):
                store = RepairStore(repair_dir)
                if store.queue_path.is_file():
                    queue_size = len(store.load_queue())
                    break
    return {
        **state,
        "queue_size": queue_size,
    }


def _analyze_cycle_summary(ctx: AnalyzerContext) -> dict[str, Any]:
    cycle = ctx.cycle_ctx
    if cycle is None:
        return {}
    bb = cycle.blackboard
    n_executed = 0
    if cycle.execution is not None:
        n_executed = len(cycle.execution.submitted or [])
    return {
        "timestamp": _utc_now(),
        "mode": cycle.config.trading_mode,
        "equity": float(bb.account.equity) if bb.account else 0.0,
        "n_candidates": len(bb.candidates or []),
        "n_proposals": len(bb.proposals or []),
        "n_executed": n_executed,
    }


def _analyze_symbol_view(ctx: AnalyzerContext) -> dict[str, Any]:
    cycle = ctx.cycle_ctx
    if cycle is None or ctx.note_path is None:
        return {}
    symbol = ctx.note_path.stem.upper()
    view = cycle.blackboard.environment.meshed_views.get(symbol)
    if view is None:
        return {"ticker": symbol}
    return {
        "ticker": symbol,
        "direction": view.effective_direction.value,
        "conviction": round(view.effective_conviction, 4),
        "rationale": view.effective_rationale[:500],
        "corroboration": view.corroboration,
        "last_cycle": _utc_now(),
    }


def _run_ruff(repo_root: Path) -> bool:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "src", "tests"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _run_pytest(repo_root: Path) -> bool:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=no"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _analyze_system_health(ctx: AnalyzerContext) -> dict[str, Any]:
    ruff_ok = _run_ruff(ctx.repo_root) if ctx.run_verify else None
    pytest_ok = _run_pytest(ctx.repo_root) if ctx.run_verify else None
    report = run_code_quality_audit(repo_root=ctx.repo_root)
    bob_status = report.worst_status.value
    result: dict[str, Any] = {
        "bob_audit_status": bob_status,
        "last_checked": _utc_now(),
    }
    if ruff_ok is not None:
        result["ruff_ok"] = ruff_ok
    if pytest_ok is not None:
        result["pytest_ok"] = pytest_ok
    return result


def _analyze_workloop_summary(ctx: AnalyzerContext) -> dict[str, Any]:
    extracted = ctx.workloop_extracted
    return {
        "source_count": int(extracted.get("source_count", 0)),
        "prior_iterations": int(extracted.get("prior_iterations", 0)),
        "plasticity_lessons": len(extracted.get("plasticity_lessons", [])),
        "last_run": _utc_now(),
    }


register("loop_engineering", _analyze_loop_engineering)
register("cycle_summary", _analyze_cycle_summary)
register("symbol_view", _analyze_symbol_view)
register("system_health", _analyze_system_health)
register("workloop_summary", _analyze_workloop_summary)


def engineering_l2_enabled(repo_root: Path) -> bool:
    state_path = repo_root / "STATE.md"
    if not state_path.is_file():
        return False
    text = state_path.read_text(encoding="utf-8")
    return bool(re.search(r"L2:\s*\*?\*?\s*enabled", text, re.IGNORECASE))
