"""Capture proposed code changes from the working tree."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def build_proposal(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    status = _git_output(root, ["status", "--porcelain"])
    diff_stat = _git_output(root, ["diff", "--stat"])
    branch = _git_output(root, ["branch", "--show-current"]).strip()
    changed = _parse_changed_files(status)

    return {
        "branch": branch,
        "changed_files": changed,
        "status_porcelain": status.strip(),
        "diff_stat": diff_stat.strip(),
        "has_changes": bool(changed),
        "summary": _summarize(changed, branch),
    }


def _git_output(root: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return proc.stderr.strip()
    return proc.stdout


def _parse_changed_files(status: str) -> list[str]:
    files: list[str] = []
    for line in status.splitlines():
        line = line.strip()
        if not line:
            continue
        # porcelain: XY path
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            files.append(parts[1])
    return files


def _summarize(changed: list[str], branch: str) -> str:
    if not changed:
        return f"No uncommitted changes on branch {branch or '(detached)'}."
    preview = ", ".join(changed[:5])
    suffix = "…" if len(changed) > 5 else ""
    return f"{len(changed)} file(s) changed on {branch or '(detached)'}: {preview}{suffix}"
