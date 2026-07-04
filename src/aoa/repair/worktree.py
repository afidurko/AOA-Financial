"""Git worktree helpers for isolated repair attempts."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def create_repair_worktree(
    repo_root: Path,
    *,
    branch: str,
    worktrees_dir: Path | None = None,
) -> dict[str, Any]:
    """Create an isolated worktree for a repair branch."""
    base = worktrees_dir or (repo_root / ".aoa-worktrees")
    base.mkdir(parents=True, exist_ok=True)
    path = base / branch.replace("/", "-")
    if path.exists():
        return {"ok": True, "path": str(path), "branch": branch, "existing": True}
    proc = subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(path), "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 and "already exists" not in (proc.stderr or ""):
        return {
            "ok": False,
            "path": str(path),
            "branch": branch,
            "error": (proc.stderr or proc.stdout or "worktree add failed").strip(),
        }
    return {"ok": True, "path": str(path), "branch": branch, "existing": False}
