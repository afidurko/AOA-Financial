"""Loop prompt shortkeys and deterministic task runners."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from aoa.repair.schedule_gate import GateAction, evaluate_gate


@dataclass(frozen=True)
class LoopPrompt:
    key: str
    title: str
    body: str
    tier: str = ""
    automation: str = ""
    cadence: str = ""


@dataclass(frozen=True)
class TaskSpec:
    key: str
    title: str
    steps: tuple[str, ...]
    on_skip: str = "log"
    on_pause: str = "exit"


@dataclass
class TaskRunResult:
    task: str
    ok: bool
    steps_run: list[str]
    gate_action: str | None = None
    message: str = ""
    exit_code: int = 0


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "aoa").is_dir():
            return parent
    return here


def prompts_path(repo_root: Path | None = None) -> Path:
    root = repo_root or find_repo_root()
    return root / "loop-prompts.yaml"


def load_prompts(repo_root: Path | None = None) -> dict[str, LoopPrompt]:
    path = prompts_path(repo_root)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, LoopPrompt] = {}
    for key, block in (data.get("prompts") or {}).items():
        if not isinstance(block, dict):
            continue
        out[str(key).upper()] = LoopPrompt(
            key=str(key).upper(),
            title=str(block.get("title", key)),
            body=str(block.get("body", "")).strip(),
            tier=str(block.get("tier", "")),
            automation=str(block.get("automation", "")),
            cadence=str(block.get("cadence", "")),
        )
    return out


def load_tasks(repo_root: Path | None = None) -> dict[str, TaskSpec]:
    path = prompts_path(repo_root)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, TaskSpec] = {}
    for key, block in (data.get("tasks") or {}).items():
        if not isinstance(block, dict):
            continue
        steps = block.get("steps") or []
        out[str(key).lower()] = TaskSpec(
            key=str(key).lower(),
            title=str(block.get("title", key)),
            steps=tuple(str(s) for s in steps),
            on_skip=str(block.get("on_skip", "log")),
            on_pause=str(block.get("on_pause", "exit")),
        )
    return out


def get_prompt(shortkey: str, *, repo_root: Path | None = None) -> LoopPrompt | None:
    return load_prompts(repo_root).get(shortkey.strip().upper())


def list_prompt_keys(*, repo_root: Path | None = None) -> list[str]:
    return sorted(load_prompts(repo_root).keys())


def list_task_keys(*, repo_root: Path | None = None) -> list[str]:
    return sorted(load_tasks(repo_root).keys())


def _append_run_log(repo_root: Path, loop: str, level: str, outcome: str, notes: str) -> None:
    log_path = repo_root / "loop-run-log.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    row = f"| {ts} | {loop} | {level} | {outcome} | {notes} |"
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        log_path.write_text(text.rstrip() + "\n" + row + "\n", encoding="utf-8")
    else:
        log_path.write_text(
            "# Loop Run Log — AOA-Financial\n\n"
            "| Timestamp (UTC) | Loop | Level | Outcome | Notes |\n"
            "|-----------------|------|-------|---------|-------|\n"
            f"{row}\n",
            encoding="utf-8",
        )


def _run_cmd(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def run_task(
    task_key: str,
    *,
    repo_root: Path | None = None,
    python: str | None = None,
) -> TaskRunResult:
    root = repo_root or find_repo_root()
    py = python or sys.executable
    tasks = load_tasks(root)
    spec = tasks.get(task_key.strip().lower())
    if spec is None:
        return TaskRunResult(
            task=task_key,
            ok=False,
            steps_run=[],
            message=f"Unknown task {task_key!r}. Try: {', '.join(list_task_keys(root))}",
            exit_code=1,
        )

    steps_run: list[str] = []
    gate_action: str | None = None

    for step in spec.steps:
        if step == "gate-triage":
            result = evaluate_gate(repo_root=root, mode="triage")
            gate_action = result.action.value
            steps_run.append(f"gate-triage={gate_action}")
            if result.action is GateAction.PAUSE:
                if spec.on_pause == "log":
                    _append_run_log(root, "maintenance", "—", "paused", f"gate pause: {result.reason}")
                return TaskRunResult(
                    task=spec.key,
                    ok=False,
                    steps_run=steps_run,
                    gate_action=gate_action,
                    message=result.reason,
                    exit_code=2,
                )
            if result.action is GateAction.SKIP:
                if spec.on_skip == "log":
                    _append_run_log(
                        root,
                        "daily-triage",
                        "L1",
                        "report-only",
                        f"skipped: {result.reason}. tokens_estimate=500",
                    )
                return TaskRunResult(
                    task=spec.key,
                    ok=True,
                    steps_run=steps_run,
                    gate_action=gate_action,
                    message=f"Skipped: {result.reason}",
                    exit_code=0,
                )
            continue

        if step == "gate-repair":
            result = evaluate_gate(repo_root=root, mode="repair")
            gate_action = result.action.value
            steps_run.append(f"gate-repair={gate_action}")
            if result.action is GateAction.PAUSE:
                return TaskRunResult(
                    task=spec.key,
                    ok=False,
                    steps_run=steps_run,
                    gate_action=gate_action,
                    message=result.reason,
                    exit_code=2,
                )
            if result.action is not GateAction.L2_ALLOWED:
                if spec.on_skip == "log":
                    _append_run_log(
                        root,
                        "fable-repair",
                        "L2",
                        "report-only",
                        f"gate blocked: {result.reason}. tokens_estimate=500",
                    )
                return TaskRunResult(
                    task=spec.key,
                    ok=True,
                    steps_run=steps_run,
                    gate_action=gate_action,
                    message=f"L2 not run: {result.reason}",
                    exit_code=0,
                )
            continue

        if step == "repair-triage":
            proc = _run_cmd([py, "-m", "aoa.cli", "repair", "triage"], cwd=root)
            steps_run.append("repair-triage")
            if proc.returncode not in (0, 1):
                return TaskRunResult(
                    task=spec.key,
                    ok=False,
                    steps_run=steps_run,
                    gate_action=gate_action,
                    message=proc.stderr or proc.stdout or "repair triage failed",
                    exit_code=proc.returncode,
                )
            continue

        if step == "verify-quick":
            proc = _run_cmd([py, "-m", "ruff", "check", "src", "tests"], cwd=root)
            steps_run.append("ruff")
            if proc.returncode != 0:
                return TaskRunResult(
                    task=spec.key,
                    ok=False,
                    steps_run=steps_run,
                    gate_action=gate_action,
                    message=proc.stdout + proc.stderr,
                    exit_code=proc.returncode,
                )
            proc = _run_cmd([py, "-m", "pytest", "-q", "--tb=no"], cwd=root)
            steps_run.append("pytest")
            if proc.returncode != 0:
                tail = (proc.stdout or "")[-800:]
                return TaskRunResult(
                    task=spec.key,
                    ok=False,
                    steps_run=steps_run,
                    gate_action=gate_action,
                    message=tail,
                    exit_code=proc.returncode,
                )
            continue

        if step == "log-triage":
            _append_run_log(
                root,
                "daily-triage",
                "L1",
                "report-only",
                f"aoa tasks run {spec.key}: repair triage + verify ok. tokens_estimate=2000",
            )
            steps_run.append("log-triage")
            continue

        return TaskRunResult(
            task=spec.key,
            ok=False,
            steps_run=steps_run,
            message=f"Unknown step {step!r}",
            exit_code=1,
        )

    return TaskRunResult(
        task=spec.key,
        ok=True,
        steps_run=steps_run,
        gate_action=gate_action,
        message=f"Task {spec.key} completed",
        exit_code=0,
    )


def format_prompt_list(repo_root: Path | None = None) -> str:
    prompts = load_prompts(repo_root)
    tasks = load_tasks(repo_root)
    lines = ["Prompt shortkeys (aoa tasks show <KEY>):", ""]
    for key in sorted(prompts):
        p = prompts[key]
        meta = " · ".join(x for x in (p.tier and f"tier {p.tier}", p.cadence) if x)
        lines.append(f"  {key:8}  {p.title}" + (f"  ({meta})" if meta else ""))
    lines.extend(["", "Task loops (aoa tasks run <name>):", ""])
    for key in sorted(tasks):
        t = tasks[key]
        lines.append(f"  {key:14}  {t.title}  → {', '.join(t.steps)}")
    return "\n".join(lines)
