"""Run verification commands (lint + tests)."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

VerifyMode = Literal["quick", "full"]

# quick: ruff only — used by repair triage (must stay fast; no nested pytest)
# full: ruff + pytest — used by workloop verify/reverify before merge
_QUICK_TIMEOUT_S = 120
_FULL_TIMEOUT_S = 600


def run_verify(
    repo_root: Path | None = None,
    *,
    mode: VerifyMode = "full",
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    started = datetime.now(timezone.utc).isoformat()
    timeout = _QUICK_TIMEOUT_S if mode == "quick" else _FULL_TIMEOUT_S
    ruff = _run_module("ruff", ["check", "src", "tests"], root, timeout=timeout)
    pytest_block: dict[str, Any] = {"ok": True, "cmd": "(skipped)", "output": "quick mode"}
    if mode == "full":
        pytest_block = _run_module("pytest", ["-q"], root, timeout=timeout)
    passed = ruff["ok"] and pytest_block["ok"]
    return {
        "ts": started,
        "mode": mode,
        "passed": passed,
        "ruff": ruff,
        "pytest": pytest_block,
    }


def _run_module(
    module: str,
    args: list[str],
    root: Path,
    *,
    timeout: int,
) -> dict[str, Any]:
    return _run_cmd([sys.executable, "-m", module, *args], root, timeout=timeout)


def _run_cmd(argv: list[str], root: Path, *, timeout: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "cmd": " ".join(argv), "output": str(exc)}
    output = (proc.stdout + proc.stderr).strip()
    return {
        "ok": proc.returncode == 0,
        "cmd": " ".join(argv),
        "returncode": proc.returncode,
        "output": output[-4000:],
    }
