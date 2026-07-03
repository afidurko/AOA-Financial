"""Merge approved branch into the base branch."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run_merge(
    proposal: dict[str, Any],
    *,
    repo_root: Path | None = None,
    base_branch: str = "main",
    allow_merge: bool = False,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    branch = str(proposal.get("branch", "")).strip()
    result: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "merged": False,
        "branch": branch,
        "base_branch": base_branch,
        "message": "",
    }

    if not allow_merge:
        result["message"] = (
            "Merge skipped — set AOA_WORKLOOP_ALLOW_MERGE=true to enable automatic merges."
        )
        return result
    if not branch or branch == base_branch:
        result["message"] = f"Already on {base_branch!r} or detached; nothing to merge."
        return result

    fetch = _git(root, ["fetch", "origin", base_branch, branch])
    if fetch["returncode"] != 0:
        result["message"] = fetch["stderr"] or "git fetch failed"
        return result

    checkout = _git(root, ["checkout", base_branch])
    if checkout["returncode"] != 0:
        result["message"] = checkout["stderr"] or f"checkout {base_branch} failed"
        return result

    pull = _git(root, ["pull", "origin", base_branch])
    if pull["returncode"] != 0:
        result["message"] = pull["stderr"] or f"pull {base_branch} failed"
        return result

    merge = _git(root, ["merge", "--no-ff", branch, "-m", f"workloop: merge {branch}"])
    if merge["returncode"] != 0:
        result["message"] = merge["stderr"] or "git merge failed"
        return result

    push = _git(root, ["push", "origin", base_branch])
    if push["returncode"] != 0:
        result["message"] = push["stderr"] or "git push failed"
        return result

    result["merged"] = True
    result["message"] = f"Merged {branch} into {base_branch} and pushed to origin."
    return result


def _git(root: Path, args: list[str]) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": 1, "stdout": "", "stderr": str(exc)}
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
