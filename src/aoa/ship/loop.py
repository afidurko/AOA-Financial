"""Ship-ready task loop — discover PR/branch issues, fix until proofread, mark ready.

Never auto-merges to main. ``ready`` means draft→ready-for-review after proofread gates pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class IssueStatus(str, Enum):
    OPEN = "open"
    FIXED = "fixed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class IssueKind(str, Enum):
    MERGE_BASE = "merge_base"
    CI = "ci"
    TESTS = "tests"
    LINT = "lint"
    CONFLICT = "conflict"
    ROSTER = "roster"
    DOCS = "docs"
    PROOFREAD = "proofread"
    DRAFT = "draft"
    CUSTOM = "custom"


@dataclass
class ShipIssue:
    id: str
    title: str
    kind: IssueKind
    status: IssueStatus = IssueStatus.OPEN
    detail: str = ""
    fix_hint: str = ""
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "status": self.status.value,
            "detail": self.detail,
            "fix_hint": self.fix_hint,
            "attempts": self.attempts,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ShipIssue:
        return cls(
            id=str(raw.get("id", "")),
            title=str(raw.get("title", "")),
            kind=IssueKind(str(raw.get("kind", "custom"))),
            status=IssueStatus(str(raw.get("status", "open"))),
            detail=str(raw.get("detail", "")),
            fix_hint=str(raw.get("fix_hint", "")),
            attempts=int(raw.get("attempts") or 0),
        )


@dataclass
class ProofreadReport:
    ok: bool
    ruff_ok: bool
    pytest_ok: bool
    notes: list[str] = field(default_factory=list)
    ruff_output: str = ""
    pytest_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShipLoopState:
    """Persisted queue for one ship-loop run on a branch/PR."""

    branch: str = ""
    pr_number: int | None = None
    issues: list[ShipIssue] = field(default_factory=list)
    proofread: ProofreadReport | None = None
    ready_for_merge: bool = False
    updated_at: str = ""
    notes: list[str] = field(default_factory=list)

    def open_issues(self) -> list[ShipIssue]:
        return [i for i in self.issues if i.status is IssueStatus.OPEN]

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "pr_number": self.pr_number,
            "issues": [i.to_dict() for i in self.issues],
            "proofread": self.proofread.to_dict() if self.proofread else None,
            "ready_for_merge": self.ready_for_merge,
            "updated_at": self.updated_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ShipLoopState:
        proof = raw.get("proofread")
        return cls(
            branch=str(raw.get("branch", "")),
            pr_number=raw.get("pr_number"),
            issues=[ShipIssue.from_dict(i) for i in (raw.get("issues") or [])],
            proofread=ProofreadReport(**proof) if isinstance(proof, dict) else None,
            ready_for_merge=bool(raw.get("ready_for_merge")),
            updated_at=str(raw.get("updated_at", "")),
            notes=list(raw.get("notes") or []),
        )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state_path(repo_root: Path) -> Path:
    return repo_root / "loop-state" / "ship-loop.json"


def load_state(path: Path) -> ShipLoopState:
    if not path.is_file():
        return ShipLoopState(updated_at=_now())
    return ShipLoopState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(state: ShipLoopState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = _now()
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=cwd)


class ShipLoopAgent:
    """Task-looping agent: discover → fix queue → proofread → ready (no auto-merge)."""

    name = "ship"
    display_name = "Ship"
    role = "PR Ship-Ready Loop"

    max_attempts_per_issue = 3

    def __init__(self, repo_root: Path, *, state_path: Path | None = None) -> None:
        self.repo_root = repo_root
        self.state_path = state_path or default_state_path(repo_root)

    def current_branch(self) -> str:
        proc = _git(self.repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        return (proc.stdout or "").strip() or "HEAD"

    def discover(
        self,
        *,
        pr_number: int | None = None,
        base: str = "origin/main",
    ) -> ShipLoopState:
        """Scan branch health and seed/refresh the issue queue."""
        state = load_state(self.state_path)
        state.branch = self.current_branch()
        if pr_number is not None:
            state.pr_number = pr_number
        known = {i.id: i for i in state.issues}
        found: list[ShipIssue] = []

        # Merge-base drift vs main
        _git(self.repo_root, "fetch", "origin", "main", "--quiet")
        counts = _git(self.repo_root, "rev-list", "--left-right", "--count", f"{base}...HEAD")
        behind, ahead = 0, 0
        if counts.returncode == 0 and counts.stdout.strip():
            parts = counts.stdout.strip().split()
            if len(parts) == 2:
                behind, ahead = int(parts[0]), int(parts[1])
        if behind > 0:
            found.append(
                ShipIssue(
                    id="merge-base",
                    title=f"Branch behind {base} by {behind} commit(s)",
                    kind=IssueKind.MERGE_BASE,
                    detail=f"behind={behind} ahead={ahead}",
                    fix_hint=f"git fetch origin main && git merge {base}",
                )
            )

        # Unmerged conflict markers in tracked sources
        markers = _run(
            ["rg", "-n", "^<<<<<<< |^=======|^>>>>>>> ", "src", "tests"],
            cwd=self.repo_root,
        )
        if markers.returncode == 0 and markers.stdout.strip():
            found.append(
                ShipIssue(
                    id="conflict-markers",
                    title="Leftover merge conflict markers",
                    kind=IssueKind.CONFLICT,
                    detail=markers.stdout.strip()[:500],
                    fix_hint="Resolve conflict markers and re-run discover",
                )
            )

        # Lint
        ruff = _run([sys.executable, "-m", "ruff", "check", "src", "tests"], cwd=self.repo_root)
        if ruff.returncode != 0:
            found.append(
                ShipIssue(
                    id="lint",
                    title="Ruff lint failures",
                    kind=IssueKind.LINT,
                    detail=(ruff.stdout or ruff.stderr or "")[:800],
                    fix_hint="python3 -m ruff check src tests --fix",
                )
            )

        # Tests (always open until proofread passes; discover notes last failure)
        pytest = _run(
            [sys.executable, "-m", "pytest", "-q", "--tb=no"],
            cwd=self.repo_root,
        )
        if pytest.returncode != 0:
            found.append(
                ShipIssue(
                    id="tests",
                    title="Pytest failures",
                    kind=IssueKind.TESTS,
                    detail=(pytest.stdout or "")[-800:],
                    fix_hint="python3 -m pytest -q",
                )
            )

        # Jim/Cindy vs ATTL twelve roster coherence
        roster_py = (self.repo_root / "src" / "aoa" / "team" / "roster.py").read_text(
            encoding="utf-8"
        )
        has_jim_agent = (self.repo_root / "src" / "aoa" / "team" / "jim.py").is_file()
        jim_in_roster = '"Jim"' in roster_py or "'Jim'" in roster_py
        if has_jim_agent and not jim_in_roster:
            decision = self.repo_root / "brain" / "decisions"
            decided = False
            if decision.is_dir():
                for p in decision.glob("*.md"):
                    text = p.read_text(encoding="utf-8")
                    if "Jim" in text and "Cindy" in text and ("specialist" in text.lower() or "outside" in text.lower() or "fourteen" in text.lower() or "14" in text):
                        decided = True
                        break
            if not decided:
                found.append(
                    ShipIssue(
                        id="roster-jim-cindy",
                        title="Jim/Cindy roster placement undecided vs ATTL twelve",
                        kind=IssueKind.ROSTER,
                        detail=(
                            "Jim/Cindy agents exist but are not on TWELVE_MEMBER_ROSTER. "
                            "Record a brain decision: specialists-outside-twelve OR expand roster."
                        ),
                        fix_hint="Write brain/decisions/*-jim-cindy-roster.md and align Aaron/UI",
                    )
                )

        # Proofread gate always required before ready
        found.append(
            ShipIssue(
                id="proofread",
                title="Independent proofread (ruff + pytest + scope)",
                kind=IssueKind.PROOFREAD,
                detail="Must pass ShipLoopAgent.proofread() before ready",
                fix_hint="aoa ship proofread",
            )
        )

        # Merge existing status for known ids
        merged: list[ShipIssue] = []
        seen: set[str] = set()
        for issue in found:
            seen.add(issue.id)
            prev = known.get(issue.id)
            if prev and prev.status is IssueStatus.FIXED and issue.kind is not IssueKind.PROOFREAD:
                # Re-open if discover still finds it
                issue.status = IssueStatus.OPEN
                issue.attempts = prev.attempts
            elif prev and issue.kind is IssueKind.PROOFREAD and state.proofread and state.proofread.ok:
                issue.status = IssueStatus.FIXED
                issue.attempts = prev.attempts
            elif prev:
                issue.attempts = prev.attempts
                if prev.status is IssueStatus.BLOCKED:
                    issue.status = IssueStatus.BLOCKED
            merged.append(issue)

        # Keep custom issues that were manually added and still open/blocked
        for iid, prev in known.items():
            if iid not in seen and prev.kind is IssueKind.CUSTOM:
                merged.append(prev)

        state.issues = merged
        state.ready_for_merge = False
        state.notes.append(f"discover @ {_now()}: {len(state.open_issues())} open")
        save_state(state, self.state_path)
        return state

    def next_issue(self) -> ShipIssue | None:
        state = load_state(self.state_path)
        for issue in state.issues:
            if issue.status is IssueStatus.OPEN:
                return issue
        return None

    def mark_fixed(self, issue_id: str, *, note: str = "") -> ShipLoopState:
        state = load_state(self.state_path)
        for issue in state.issues:
            if issue.id == issue_id:
                issue.status = IssueStatus.FIXED
                if note:
                    issue.detail = note
                break
        state.notes.append(f"fixed {issue_id} @ {_now()}")
        save_state(state, self.state_path)
        return state

    def mark_attempt(self, issue_id: str, *, blocked: bool = False, detail: str = "") -> ShipLoopState:
        state = load_state(self.state_path)
        for issue in state.issues:
            if issue.id == issue_id:
                issue.attempts += 1
                if detail:
                    issue.detail = detail
                if blocked or issue.attempts >= self.max_attempts_per_issue:
                    issue.status = IssueStatus.BLOCKED
                break
        save_state(state, self.state_path)
        return state

    def proofread(self) -> ProofreadReport:
        """Checker gate: lint + tests must pass. Does not trust prior claims."""
        notes: list[str] = []
        ruff = _run([sys.executable, "-m", "ruff", "check", "src", "tests"], cwd=self.repo_root)
        ruff_ok = ruff.returncode == 0
        if not ruff_ok:
            notes.append("ruff failed")
        pytest = _run(
            [sys.executable, "-m", "pytest", "-q", "--tb=line"],
            cwd=self.repo_root,
        )
        pytest_ok = pytest.returncode == 0
        if not pytest_ok:
            notes.append("pytest failed")

        # Conflict markers
        markers = _run(
            ["rg", "-n", "^<<<<<<< |^=======|^>>>>>>> ", "src", "tests"],
            cwd=self.repo_root,
        )
        if markers.returncode == 0 and markers.stdout.strip():
            notes.append("conflict markers present")
            ruff_ok = False  # fail proofread

        ok = ruff_ok and pytest_ok and not any(n.startswith("conflict") for n in notes)
        report = ProofreadReport(
            ok=ok,
            ruff_ok=ruff_ok,
            pytest_ok=pytest_ok,
            notes=notes or (["proofread passed"] if ok else []),
            ruff_output=(ruff.stdout or ruff.stderr or "")[:1000],
            pytest_output=(pytest.stdout or "")[-1000:],
        )
        state = load_state(self.state_path)
        state.proofread = report
        for issue in state.issues:
            if issue.id == "proofread":
                issue.status = IssueStatus.FIXED if ok else IssueStatus.OPEN
                issue.detail = "; ".join(report.notes)
        if not ok:
            state.ready_for_merge = False
        state.notes.append(f"proofread ok={ok} @ {_now()}")
        save_state(state, self.state_path)
        return report

    def can_mark_ready(self) -> tuple[bool, str]:
        state = load_state(self.state_path)
        open_ids = [i.id for i in state.open_issues()]
        if open_ids:
            return False, f"Open issues remain: {', '.join(open_ids)}"
        if state.proofread is None or not state.proofread.ok:
            return False, "Proofread has not passed"
        blocked = [i.id for i in state.issues if i.status is IssueStatus.BLOCKED]
        if blocked:
            return False, f"Blocked issues: {', '.join(blocked)}"
        return True, "All ship-loop gates passed (ready for human merge; no auto-merge)"

    def mark_ready(self) -> ShipLoopState:
        ok, msg = self.can_mark_ready()
        state = load_state(self.state_path)
        if not ok:
            state.ready_for_merge = False
            state.notes.append(f"ready denied: {msg}")
            save_state(state, self.state_path)
            raise RuntimeError(msg)
        state.ready_for_merge = True
        state.notes.append(f"ready_for_merge=true @ {_now()} — {msg}")
        save_state(state, self.state_path)
        return state

    def status(self) -> dict[str, Any]:
        state = load_state(self.state_path)
        ok, msg = self.can_mark_ready()
        return {
            **state.to_dict(),
            "open_count": len(state.open_issues()),
            "can_mark_ready": ok,
            "ready_message": msg,
        }
