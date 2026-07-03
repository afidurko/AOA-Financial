"""Run verification commands (lint + tests)."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run_verify(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    started = datetime.now(timezone.utc).isoformat()
    ruff = _run_cmd(_ruff_cmd(), ["check", "src", "tests"], root)
    pytest = _run_cmd(_pytest_cmd(), ["-q"], root)
    passed = ruff["ok"] and pytest["ok"]
    return {
        "ts": started,
        "passed": passed,
        "ruff": ruff,
        "pytest": pytest,
    }


def _ruff_cmd() -> str:
    return shutil.which("ruff") or "ruff"


def _pytest_cmd() -> str:
    return shutil.which("pytest") or "pytest"


def _run_cmd(cmd: str, args: list[str], root: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [cmd, *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "cmd": f"{cmd} {' '.join(args)}", "output": str(exc)}
    output = (proc.stdout + proc.stderr).strip()
    return {
        "ok": proc.returncode == 0,
        "cmd": f"{cmd} {' '.join(args)}",
        "returncode": proc.returncode,
        "output": output[-4000:],
    }
