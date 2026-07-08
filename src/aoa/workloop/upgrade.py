"""Upgrade project dependencies before final verification."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aoa.workloop.verify import run_verify


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


def run_upgrade_pipeline(
    repo_root: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Verify → pip upgrade (optional) → reverify. Used by `aoa workloop upgrade`."""
    root = repo_root or Path.cwd()
    baseline = run_verify(root, mode="quick")
    if not baseline.get("passed"):
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "dry_run": dry_run,
            "phase": "baseline-verify",
            "baseline": baseline,
        }
    if dry_run:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ok": True,
            "dry_run": True,
            "phase": "skipped",
            "baseline": baseline,
            "upgrade": {"ok": True, "message": "Dry-run: upgrade skipped."},
            "reverify": baseline,
        }
    upgrade = run_upgrade(root)
    reverify = run_verify(root, mode="quick")
    ok = bool(upgrade.get("ok")) and bool(reverify.get("passed"))
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "dry_run": False,
        "phase": "complete",
        "baseline": baseline,
        "upgrade": upgrade,
        "reverify": reverify,
    }
