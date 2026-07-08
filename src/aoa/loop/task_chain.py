"""Automatic next-task chaining from docs/upgrade-backlog.json.

When an L2 item completes, advance the chain: skip human-only tasks, queue the
next automatable item in STATE.md, and only surface alerts when automation stops.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from aoa.loop.prompts import find_repo_root


class ChainAction(str, Enum):
    QUEUED = "queued"
    ALL_DONE = "all_done"
    ALERT_HUMAN = "alert_human"


@dataclass(frozen=True)
class BacklogItem:
    item_id: str
    title: str
    skill: str
    automatable: bool
    detail: str
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChainState:
    updated_at: str
    completed: tuple[str, ...]
    last_completed: str
    current: str
    skipped_human: tuple[str, ...]
    alerts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "completed": list(self.completed),
            "last_completed": self.last_completed,
            "current": self.current,
            "skipped_human": list(self.skipped_human),
            "alerts": list(self.alerts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainState:
        return cls(
            updated_at=str(data.get("updated_at", "")),
            completed=tuple(str(x) for x in data.get("completed", [])),
            last_completed=str(data.get("last_completed", "")),
            current=str(data.get("current", "")),
            skipped_human=tuple(str(x) for x in data.get("skipped_human", [])),
            alerts=tuple(str(x) for x in data.get("alerts", [])),
        )


@dataclass(frozen=True)
class AdvanceResult:
    action: ChainAction
    completed_id: str
    next_id: str
    next_item: BacklogItem | None
    skipped_human_ids: tuple[str, ...]
    alert_message: str
    state: ChainState

    @property
    def exit_code(self) -> int:
        if self.action is ChainAction.ALERT_HUMAN:
            return 3
        return 0


def backlog_path(repo_root: Path | None = None) -> Path:
    return (repo_root or find_repo_root()) / "docs" / "upgrade-backlog.json"


def chain_state_path(repo_root: Path | None = None, *, env: str = "paper-dry") -> Path:
    root = repo_root or find_repo_root()
    return root / "data" / env / "loop" / "task-chain.json"


def load_backlog(repo_root: Path | None = None) -> tuple[list[str], dict[str, BacklogItem], list[str]]:
    path = backlog_path(repo_root)
    if not path.is_file():
        raise FileNotFoundError(f"Upgrade backlog not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    sequence = [str(x) for x in data.get("recommended_sequence", [])]
    assumed = [str(x) for x in data.get("assumed_completed", [])]
    raw_items = data.get("items") or {}
    items: dict[str, BacklogItem] = {}
    for item_id, block in raw_items.items():
        if not isinstance(block, dict):
            continue
        skill = str(block.get("skill", "minimal-fix"))
        automatable = bool(block.get("automatable", skill not in {"human"}))
        files = block.get("files") or []
        items[str(item_id)] = BacklogItem(
            item_id=str(item_id),
            title=str(block.get("title", item_id)),
            skill=skill,
            automatable=automatable,
            detail=str(block.get("detail", "")),
            files=tuple(str(f) for f in files),
        )
    return sequence, items, assumed


def load_chain_state(
    repo_root: Path | None = None,
    *,
    env: str = "paper-dry",
) -> ChainState:
    path = chain_state_path(repo_root, env=env)
    if not path.is_file():
        sequence, _, _ = load_backlog(repo_root)
        first = sequence[0] if sequence else ""
        return ChainState(
            updated_at="",
            completed=(),
            last_completed="",
            current=first,
            skipped_human=(),
            alerts=(),
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return ChainState.from_dict(data)


def save_chain_state(
    state: ChainState,
    repo_root: Path | None = None,
    *,
    env: str = "paper-dry",
) -> Path:
    path = chain_state_path(repo_root, env=env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def _next_candidates(
    sequence: list[str],
    items: dict[str, BacklogItem],
    *,
    completed: set[str],
    skipped_human: set[str],
    after_id: str | None = None,
) -> list[str]:
    if after_id and after_id in sequence:
        start = sequence.index(after_id) + 1
        tail = sequence[start:]
        head = [x for x in sequence[:start] if x not in tail]
        ordered = tail + head
    else:
        ordered = list(sequence)
    out: list[str] = []
    for item_id in ordered:
        if item_id in completed or item_id in skipped_human:
            continue
        if item_id not in items:
            continue
        out.append(item_id)
    return out


def resolve_next_automatable(
    sequence: list[str],
    items: dict[str, BacklogItem],
    *,
    completed: set[str],
    skipped_human: set[str],
    after_id: str | None = None,
) -> tuple[str | None, tuple[str, ...]]:
    """Return (next_automatable_id, human_ids_skipped_while_searching)."""
    human_skipped: list[str] = []
    for item_id in _next_candidates(
        sequence, items, completed=completed, skipped_human=skipped_human, after_id=after_id
    ):
        item = items[item_id]
        if item.automatable and item.skill != "human":
            return item_id, tuple(human_skipped)
        human_skipped.append(item_id)
    return None, tuple(human_skipped)


def advance_chain(
    completed_id: str,
    *,
    repo_root: Path | None = None,
    env: str = "paper-dry",
) -> AdvanceResult:
    root = repo_root or find_repo_root()
    sequence, items, _ = load_backlog(root)
    if completed_id not in items:
        raise ValueError(f"Unknown backlog item {completed_id!r}")

    state = load_chain_state(root, env=env)
    completed = set(state.completed)
    skipped_human = set(state.skipped_human)
    completed.add(completed_id)

    next_id, newly_skipped = resolve_next_automatable(
        sequence,
        items,
        completed=completed,
        skipped_human=skipped_human,
        after_id=completed_id,
    )
    skipped_human.update(newly_skipped)

    alerts = list(state.alerts)
    action = ChainAction.ALL_DONE
    next_item: BacklogItem | None = None
    alert_message = ""

    if next_id is None:
        if newly_skipped:
            action = ChainAction.ALERT_HUMAN
            titles = ", ".join(items[i].title for i in newly_skipped if i in items)
            alert_message = (
                f"Upgrade chain blocked: remaining items need a human — {titles}. "
                f"Completed {completed_id!r}; no automatable work left."
            )
            alerts.append(alert_message)
        else:
            alert_message = f"Upgrade chain complete after {completed_id!r}."
    else:
        action = ChainAction.QUEUED
        next_item = items[next_id]
        alert_message = f"Queued {next_id}: {next_item.title}"

    new_state = ChainState(
        updated_at=datetime.now(timezone.utc).isoformat(),
        completed=tuple(sorted(completed)),
        last_completed=completed_id,
        current=next_id or "",
        skipped_human=tuple(sorted(skipped_human)),
        alerts=tuple(alerts[-20:]),
    )
    save_chain_state(new_state, root, env=env)
    sync_state_high_priority(root, next_item, env=env)

    return AdvanceResult(
        action=action,
        completed_id=completed_id,
        next_id=next_id or "",
        next_item=next_item,
        skipped_human_ids=newly_skipped,
        alert_message=alert_message,
        state=new_state,
    )


def sync_state_high_priority(
    repo_root: Path | None = None,
    item: BacklogItem | None = None,
    *,
    env: str = "paper-dry",
) -> None:
    """Write the current automatable task into STATE.md High Priority."""
    root = repo_root or find_repo_root()
    state_path = root / "STATE.md"
    if item is None:
        chain = load_chain_state(root, env=env)
        if not chain.current:
            _replace_high_priority(state_path, none=True)
            return
        _, items, _ = load_backlog(root)
        item = items.get(chain.current)
        if item is None:
            _replace_high_priority(state_path, none=True)
            return

    line = (
        f"- **{item.title}** — {item.detail}  \n"
        f"  Source: `upgrade-backlog` | Skill: `{item.skill}` | id: `{item.item_id}`"
    )
    _replace_high_priority(state_path, line=line)


def _replace_high_priority(
    state_path: Path,
    *,
    line: str | None = None,
    none: bool = False,
) -> None:
    if not state_path.is_file():
        return
    text = state_path.read_text(encoding="utf-8")
    replacement = "_(none — chain waiting or complete)_" if none else line or ""
    pattern = re.compile(
        r"(## High Priority \(loop is acting or waiting on human\)\n\n)"
        r"(?:.*?\n\n)(?=## )",
        re.DOTALL,
    )
    if not pattern.search(text):
        return
    new_block = f"\\1{replacement}\n\n"
    state_path.write_text(pattern.sub(new_block, text, count=1), encoding="utf-8")


def bootstrap_chain_from_state(
    repo_root: Path | None = None,
    *,
    env: str = "paper-dry",
) -> ChainState:
    """Initialize chain: seed assumed_completed, skip human tasks, queue next automatable."""
    root = repo_root or find_repo_root()
    sequence, items, assumed = load_backlog(root)
    path = chain_state_path(root, env=env)
    if path.is_file():
        state = load_chain_state(root, env=env)
        if state.current and state.current in items:
            sync_state_high_priority(root, items[state.current], env=env)
            return state
        completed = set(state.completed)
    else:
        completed = set(assumed)

    skipped = set(load_chain_state(root, env=env).skipped_human)
    after = assumed[-1] if assumed else None
    next_id, skipped_new = resolve_next_automatable(
        sequence, items, completed=completed, skipped_human=skipped, after_id=after
    )
    skipped.update(skipped_new)
    new_state = ChainState(
        updated_at=datetime.now(timezone.utc).isoformat(),
        completed=tuple(sorted(completed)),
        last_completed=assumed[-1] if assumed else "",
        current=next_id or "",
        skipped_human=tuple(sorted(skipped)),
        alerts=(),
    )
    save_chain_state(new_state, root, env=env)
    if next_id:
        sync_state_high_priority(root, items[next_id], env=env)
    else:
        sync_state_high_priority(root, None, env=env)
    return new_state


def chain_status(
    repo_root: Path | None = None,
    *,
    env: str = "paper-dry",
) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    sequence, items, _ = load_backlog(root)
    state = load_chain_state(root, env=env)
    current_item = items.get(state.current) if state.current else None
    return {
        "backlog": str(backlog_path(root)),
        "chain_state": str(chain_state_path(root, env=env)),
        "sequence": sequence,
        "completed": list(state.completed),
        "current": state.current,
        "current_title": current_item.title if current_item else None,
        "current_automatable": bool(current_item and current_item.automatable),
        "skipped_human": list(state.skipped_human),
        "alerts": list(state.alerts),
    }


def format_advance_result(result: AdvanceResult) -> str:
    lines = [
        f"action: {result.action.value}",
        f"completed: {result.completed_id}",
        f"message: {result.alert_message}",
    ]
    if result.skipped_human_ids:
        lines.append(f"skipped_human: {', '.join(result.skipped_human_ids)}")
    if result.next_item:
        lines.append(f"next: {result.next_id} ({result.next_item.skill})")
    return "\n".join(lines)
