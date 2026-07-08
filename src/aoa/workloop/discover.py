"""Discover learning materials and local databases."""

from __future__ import annotations

import subprocess
from pathlib import Path

from aoa.config import Config
from aoa.workloop.models import LearningSource


def discover_sources(config: Config, repo_root: Path | None = None) -> list[LearningSource]:
    root = repo_root or Path.cwd()
    sources: list[LearningSource] = []

    _add_file_source(sources, "journal", config.journal_path, "Trading decision audit log")
    _add_file_source(sources, "plasticity", config.plasticity_path, "Cross-cycle plastic memory")
    _add_file_source(sources, "ci", root / ".github/workflows/ci.yml", "CI verification pipeline")
    _add_file_source(sources, "readme", root / "README.md", "Project architecture and operations")
    _add_file_source(sources, "loop_state", root / "STATE.md", "Daily triage state and watch list")
    _add_file_source(sources, "loop_config", root / "LOOP.md", "Loop cadence, skills, and run order")
    _add_file_source(
        sources,
        "loop_constraints",
        root / "loop-constraints.md",
        "Binding guardrails for agent loops",
    )
    _add_file_source(
        sources,
        "loop_run_log",
        root / "loop-run-log.md",
        "Loop run history and budget events",
    )
    _add_dir_source(sources, "tests", root / "tests", "Regression and integration tests")
    _add_dir_source(sources, "profiles", root / "profiles", "Environment profiles")
    _add_dir_source(sources, "agents", root / "src/aoa/agents", "Specialist agent implementations")
    _add_dir_source(sources, "swarm", root / "src/aoa/swarm", "Pipeline orchestration")
    _add_workloop_store(sources, config)
    _add_vault_source(sources, config, root)

    for extra in config.workloop_extra_sources:
        path = Path(extra)
        if path.is_file():
            _add_file_source(sources, "extra", path, "Configured learning source")
        elif path.is_dir():
            _add_dir_source(sources, "extra", path, "Configured learning source")

    git_source = _git_recent_summary(root)
    if git_source is not None:
        sources.append(git_source)

    return sources


def _add_file_source(
    sources: list[LearningSource],
    kind: str,
    path: Path,
    summary: str,
) -> None:
    if not path.exists():
        return
    stat = path.stat()
    sources.append(
        LearningSource(
            kind=kind,
            path=str(path),
            summary=summary,
            metadata={"bytes": stat.st_size, "exists": True},
        )
    )


def _add_dir_source(
    sources: list[LearningSource],
    kind: str,
    path: Path,
    summary: str,
) -> None:
    if not path.is_dir():
        return
    files = [p for p in path.rglob("*") if p.is_file() and not _is_ignored(p)]
    sources.append(
        LearningSource(
            kind=kind,
            path=str(path),
            summary=summary,
            metadata={"file_count": len(files), "exists": True},
        )
    )


def _add_workloop_store(sources: list[LearningSource], config: Config) -> None:
    store_root = config.workloop_path
    if not store_root.exists():
        return
    files = [p for p in store_root.rglob("*") if p.is_file()]
    sources.append(
        LearningSource(
            kind="workloop_store",
            path=str(store_root),
            summary="Prior work-loop runs, learnings, and approvals",
            metadata={"file_count": len(files)},
        )
    )


def _add_vault_source(sources: list[LearningSource], config: Config, root: Path) -> None:
    vault_rel = getattr(config, "vault_path", "vault") or "vault"
    vault_path = Path(vault_rel)
    if not vault_path.is_absolute():
        vault_path = root / vault_path
    if not vault_path.is_dir():
        return
    files = [p for p in vault_path.rglob("*.md") if p.is_file() and not p.name.startswith("_")]
    sources.append(
        LearningSource(
            kind="vault",
            path=str(vault_path),
            summary="Schema-driven knowledge vault with auto-synced properties",
            metadata={"file_count": len(files), "exists": True},
        )
    )


def _is_ignored(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"})


def _git_recent_summary(root: Path) -> LearningSource | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "--oneline", "-n", "8"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    commits = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return LearningSource(
        kind="git_history",
        path=str(root / ".git"),
        summary="Recent repository commits",
        metadata={"recent_commits": commits},
    )
