"""Discover repair candidates from audits, verification, and loop state."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from aoa.repair.models import RepairItem
from aoa.team.code_engineering import run_code_quality_audit
from aoa.team.models import HealthStatus
from aoa.workloop.verify import run_verify


def discover_repairs(
    *,
    repo_root: Path | None = None,
    state_path: Path | None = None,
) -> list[RepairItem]:
    root = repo_root or Path.cwd()
    items: list[RepairItem] = []

    audit = run_code_quality_audit(repo_root=root)
    for finding in audit.findings:
        if finding.status is HealthStatus.OK:
            continue
        severity = "critical" if finding.status is HealthStatus.CRITICAL else "degraded"
        items.append(
            RepairItem(
                item_id=_new_id(),
                title=f"Code audit: {finding.area}",
                source="code_audit",
                severity=severity,
                fixable=finding.area not in {"imports"},
                detail=finding.detail,
                suggested_skill="coding-engineer" if finding.area != "ruff" else "minimal-fix",
            )
        )

    verify = run_verify(root)
    if not verify.get("passed"):
        for key in ("ruff", "pytest"):
            block = verify.get(key, {})
            if not block.get("ok"):
                items.append(
                    RepairItem(
                        item_id=_new_id(),
                        title=f"Verify failed: {key}",
                        source="verify",
                        severity="critical",
                        fixable=True,
                        detail=str(block.get("output", block.get("cmd", "")))[:500],
                        suggested_skill="minimal-fix",
                    )
                )

    if state_path is not None and state_path.is_file():
        items.extend(_items_from_state(state_path))

    return _dedupe(items)


def _items_from_state(state_path: Path) -> list[RepairItem]:
    text = state_path.read_text(encoding="utf-8")
    items: list[RepairItem] = []
    section = ""
    for line in text.splitlines():
        if line.startswith("## High Priority"):
            section = "high"
            continue
        if line.startswith("## Watch List"):
            section = "watch"
            continue
        if line.startswith("## "):
            section = ""
            continue
        if not line.strip().startswith("- **") or section not in {"high", "watch"}:
            continue
        match = re.match(r"- \*\*(.+?)\*\* — (.+)", line.strip())
        if not match:
            continue
        title, detail = match.group(1), match.group(2)
        if title.startswith("_") or "none" in title.lower():
            continue
        items.append(
            RepairItem(
                item_id=_new_id(),
                title=title,
                source="state",
                severity="critical" if section == "high" else "watch",
                fixable=section == "high",
                detail=detail,
                suggested_skill="fable-repair",
            )
        )
    return items


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _dedupe(items: list[RepairItem]) -> list[RepairItem]:
    seen: set[str] = set()
    out: list[RepairItem] = []
    for item in items:
        key = f"{item.source}:{item.title}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
