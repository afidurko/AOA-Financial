"""Fable 5 repair-loop orchestrator (discover → queue → sync STATE.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aoa.config import Config
from aoa.repair.discovery import discover_repairs
from aoa.repair.models import RepairItem, RepairRun
from aoa.repair.store import RepairStore
from aoa.repair.worktree import create_repair_worktree


@dataclass
class RepairResult:
    run: RepairRun
    queue_path: Path
    state_path: Path


class RepairOrchestrator:
    """Deterministic repair discovery wired to loop-engineering state files."""

    def __init__(
        self,
        config: Config,
        *,
        repo_root: Path | None = None,
        store: RepairStore | None = None,
    ) -> None:
        self.config = config
        self.repo_root = repo_root or _find_repo_root()
        self.store = store or RepairStore(config.repair_path)
        self.state_path = self.repo_root / "STATE.md"

    def triage(self, *, sync_state: bool = True) -> RepairResult:
        items = discover_repairs(
            repo_root=self.repo_root,
            state_path=self.state_path if self.state_path.is_file() else None,
        )
        self.store.save_queue(items)
        run = RepairRun(
            run_id=self.store.new_run_id(),
            status="completed",
            items=items,
            notes=[f"Discovered {len(items)} repair candidate(s)."],
        )
        self.store.record("repair.triage", {"run_id": run.run_id, "count": len(items)})
        if sync_state and self.config.repair_sync_state:
            _sync_state_md(self.state_path, items, run.run_id)
            if self.config.vault_sync_enabled:
                from aoa.vault.sync import sync_vault_engineering

                sync_vault_engineering(
                    self.config,
                    repo_root=self.repo_root,
                    dry_run=None,
                    run_verify=False,
                )
        return RepairResult(
            run=run,
            queue_path=self.store.queue_path,
            state_path=self.state_path,
        )

    def prepare_worktree(self, *, item_id: str | None = None) -> dict:
        branch = f"repair/{item_id or self.store.new_run_id()}"
        return create_repair_worktree(
            self.repo_root,
            branch=branch,
            worktrees_dir=self.repo_root / self.config.repair_worktrees_dir,
        )

    def queue(self) -> list[RepairItem]:
        return self.store.load_queue()


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "aoa").exists():
            return parent
    return Path.cwd()


def _sync_state_md(state_path: Path, items: list[RepairItem], run_id: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    high = [i for i in items if i.severity == "critical" and i.fixable]
    watch = [i for i in items if i.severity in {"degraded", "watch"} or not i.fixable]
    preserved = _preserve_state_sections(
        state_path,
        ("## Loop automation", "## Next actions"),
    )

    lines = [
        "# Loop State — AOA-Financial",
        "",
        f"Last run: {now} (Fable 5 repair triage, run {run_id})",
        "",
        "## High Priority (loop is acting or waiting on human)",
        "",
    ]
    if high:
        for item in high:
            lines.append(
                f"- **{item.title}** — {item.detail[:200]}"
                f"  \n  Source: `{item.source}` | Skill: `{item.suggested_skill}` | id: `{item.item_id}`"
            )
    else:
        lines.append("_(none — system healthy or only watch items)_")

    lines.extend(["", "## Watch List", ""])
    if watch:
        for item in watch:
            lines.append(f"- **{item.title}** — {item.detail[:200]}")
    else:
        lines.append("_(none)_")

    if preserved:
        lines.append("")
        lines.extend(preserved)

    lines.extend(
        [
            "",
            "## Repair queue",
            "",
            f"Machine-readable queue: `data/{{AOA_ENV}}/repair/queue.json` ({len(items)} items)",
            "",
            "---",
            "Run log: loop-run-log.md",
            "",
        ]
    )
    state_path.write_text("\n".join(lines), encoding="utf-8")


def _preserve_state_sections(state_path: Path, headers: tuple[str, ...]) -> list[str]:
    """Keep human-edited sections across repair triage syncs."""
    if not state_path.is_file():
        return []
    text = state_path.read_text(encoding="utf-8")
    out: list[str] = []
    for header in headers:
        block = _extract_section(text, header)
        if block:
            out.extend(block)
            if not block[-1].strip():
                pass
            else:
                out.append("")
    while out and not out[-1].strip():
        out.pop()
    return out


def _extract_section(text: str, header: str) -> list[str]:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header.strip():
            start = i
            break
    if start is None:
        return []
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## ") and lines[j].strip() != header.strip():
            end = j
            break
    block = lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    return block
