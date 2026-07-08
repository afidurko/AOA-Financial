"""Vault note store — Markdown with YAML frontmatter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class VaultNote:
    path: Path
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @property
    def note_type(self) -> str:
        return str(self.frontmatter.get("type", ""))

    @property
    def locked_properties(self) -> set[str]:
        locked = self.frontmatter.get("locked", [])
        if isinstance(locked, list):
            return {str(x) for x in locked}
        return set()


def read_note(path: Path) -> VaultNote:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return VaultNote(path=path, body=text)
    fm = yaml.safe_load(match.group(1)) or {}
    if not isinstance(fm, dict):
        fm = {}
    body = text[match.end() :]
    return VaultNote(path=path, frontmatter=fm, body=body)


def write_note(note: VaultNote) -> None:
    fm_text = yaml.safe_dump(
        note.frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    body = note.body
    if body and not body.startswith("\n"):
        body = "\n" + body
    note.path.parent.mkdir(parents=True, exist_ok=True)
    note.path.write_text(f"---\n{fm_text}\n---{body}", encoding="utf-8")


def list_notes(vault_root: Path) -> list[Path]:
    if not vault_root.is_dir():
        return []
    notes: list[Path] = []
    for path in sorted(vault_root.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        notes.append(path)
    return notes


def apply_property_updates(
    note: VaultNote,
    updates: dict[str, Any],
    *,
    locked: set[str] | None = None,
) -> dict[str, tuple[Any, Any]]:
    """Merge updates into frontmatter. Returns changed properties (old, new)."""
    locked_set = locked if locked is not None else note.locked_properties
    changed: dict[str, tuple[Any, Any]] = {}
    for key, new_val in updates.items():
        if key in locked_set or key == "locked":
            continue
        old_val = note.frontmatter.get(key)
        if _values_equal(old_val, new_val):
            continue
        changed[key] = (old_val, new_val)
        note.frontmatter[key] = new_val
    return changed


def _values_equal(a: Any, b: Any) -> bool:
    if a is None and b in ("", 0, 0.0, False):
        return True
    if b is None and a in ("", 0, 0.0, False):
        return True
    if isinstance(a, float) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return a == b
