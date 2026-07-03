"""Execute approved code changes."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def execute_changes(
    proposal: dict[str, Any],
    *,
    repo_root: Path | None = None,
    auto_commit: bool = False,
    commit_message: str = "",
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    changed = list(proposal.get("changed_files", []))
    result: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "changed_files": changed,
        "committed": False,
        "commit_sha": "",
        "message": "",
    }

    if not changed:
        result["message"] = "No working-tree changes to execute."
        return result

    if not auto_commit:
        result["message"] = (
            f"Approved execution acknowledged for {len(changed)} file(s); "
            "auto-commit disabled (set AOA_WORKLOOP_AUTO_COMMIT=true to commit)."
        )
        return result

    msg = commit_message or _default_commit_message(proposal)
    add = subprocess.run(
        ["git", "-C", str(root), "add", "-A"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if add.returncode != 0:
        result["message"] = add.stderr.strip() or "git add failed"
        return result

    commit = subprocess.run(
        ["git", "-C", str(root), "commit", "-m", msg],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if commit.returncode != 0:
        result["message"] = commit.stderr.strip() or "git commit failed"
        return result

    sha = _git_output(root, ["rev-parse", "HEAD"]).strip()
    result["committed"] = True
    result["commit_sha"] = sha
    result["message"] = f"Committed {len(changed)} file(s) as {sha[:8]}."
    return result


def _default_commit_message(proposal: dict[str, Any]) -> str:
    branch = proposal.get("branch", "")
    summary = proposal.get("summary", "Work-loop approved changes")
    return f"workloop: {summary} ({branch})"


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
        return ""
    return proc.stdout
