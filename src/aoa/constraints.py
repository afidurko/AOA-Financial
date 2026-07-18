"""Load and classify loop-constraints.md for programmatic mesh enforcement."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SECTION = re.compile(r"^##\s+(.+?)\s*$")
_BULLET = re.compile(r"^[-*]\s+\*?\*?(.+?)\*?\*?\s*$")
_NUMBERED = re.compile(r"^\d+\.\s+(.+)$")


@dataclass
class ConstraintSet:
    """Parsed constraints with hard-floor vs policy split."""

    path: Path
    hard_floor: list[str] = field(default_factory=list)
    attl_policy: list[str] = field(default_factory=list)
    other: dict[str, list[str]] = field(default_factory=dict)
    pause_active: bool = False
    mode: str = "auto-12"
    review_policy: str = "critical_only"

    @property
    def rule_count(self) -> int:
        n = len(self.hard_floor) + len(self.attl_policy)
        for rules in self.other.values():
            n += len(rules)
        return n

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "rule_count": self.rule_count,
            "hard_floor": list(self.hard_floor),
            "attl_policy": list(self.attl_policy),
            "other": {k: list(v) for k, v in self.other.items()},
            "pause_active": self.pause_active,
            "mode": self.mode,
            "review_policy": self.review_policy,
        }


def load_constraints(repo_root: Path | None = None) -> ConstraintSet:
    """Parse loop-constraints.md and detect loop-pause-all in STATE.md."""
    root = repo_root or Path.cwd()
    path = root / "loop-constraints.md"
    cs = ConstraintSet(path=path)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        current = ""
        for line in text.splitlines():
            sec = _SECTION.match(line)
            if sec:
                current = sec.group(1).strip().lower()
                continue
            rule = _extract_rule(line)
            if not rule:
                continue
            if "hard safety floor" in current:
                cs.hard_floor.append(rule)
            elif "attl" in current or "auto-12" in current:
                cs.attl_policy.append(rule)
            elif current:
                cs.other.setdefault(current, []).append(rule)
            else:
                cs.other.setdefault("preamble", []).append(rule)
        if "auto-12" in text.lower():
            cs.mode = "auto-12"
        if "critical-only" in text.lower() or "critical_only" in text.lower():
            cs.review_policy = "critical_only"
    cs.pause_active = _pause_active(root)
    return cs


def assert_not_paused(repo_root: Path | None = None) -> ConstraintSet:
    """Load constraints; raise RuntimeError if pause is active."""
    cs = load_constraints(repo_root)
    if cs.pause_active:
        raise RuntimeError("loop-pause-all is active in STATE.md — ATTL/mesh halted.")
    return cs


def _extract_rule(line: str) -> str:
    stripped = line.strip()
    m = _BULLET.match(stripped) or _NUMBERED.match(stripped)
    if not m:
        return ""
    return m.group(1).strip()


def _pause_active(repo_root: Path) -> bool:
    state = repo_root / "STATE.md"
    if not state.is_file():
        return False
    text = state.read_text(encoding="utf-8")
    return "loop-pause-all" in text.lower()
