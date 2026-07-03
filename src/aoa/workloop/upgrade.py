"""Upgrade project dependencies before final verification."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run_upgrade(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-e",
        ".[dev,web]",
        "--upgrade",
        "-q",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "cmd": " ".join(cmd),
            "output": str(exc),
        }
    output = (proc.stdout + proc.stderr).strip()
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": proc.returncode == 0,
        "cmd": " ".join(cmd),
        "returncode": proc.returncode,
        "output": output[-4000:],
    }
