"""Deterministic integrity checks for code, workspaces, neural memory, and mesh."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from aoa.brain.store import BrainStore, ensure_brain_workspace
from aoa.constraints import load_constraints
from aoa.plasticity.memory import load_memory
from aoa.team.code_engineering import run_code_quality_audit
from aoa.team.models import HealthStatus
from aoa.team.roster import TWELVE_MEMBER_ROSTER, roster_names
from aoa.workspaces import probe_workspaces


class IntegritySeverity(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    CRITICAL = "critical"


@dataclass
class IntegrityFinding:
    domain: str
    agent: str
    status: IntegritySeverity
    detail: str
    automatable: bool = False
    fix_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "agent": self.agent,
            "status": self.status.value,
            "detail": self.detail,
            "automatable": self.automatable,
            "fix_hint": self.fix_hint,
        }


@dataclass
class DomainReport:
    domain: str
    agent: str
    status: IntegritySeverity
    findings: list[IntegrityFinding] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "agent": self.agent,
            "status": self.status.value,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
        }


def _worst(statuses: list[IntegritySeverity]) -> IntegritySeverity:
    order = {
        IntegritySeverity.OK: 0,
        IntegritySeverity.DEGRADED: 1,
        IntegritySeverity.CRITICAL: 2,
    }
    worst = IntegritySeverity.OK
    for s in statuses:
        if order[s] > order[worst]:
            worst = s
    return worst


def _from_health(status: HealthStatus) -> IntegritySeverity:
    if status is HealthStatus.CRITICAL:
        return IntegritySeverity.CRITICAL
    if status is HealthStatus.DEGRADED:
        return IntegritySeverity.DEGRADED
    return IntegritySeverity.OK


def check_code(repo_root: Path) -> DomainReport:
    """Bob — code & systems integrity via coding-engineer audit."""
    audit = run_code_quality_audit(repo_root=repo_root)
    findings = [
        IntegrityFinding(
            domain="code",
            agent="Bob",
            status=_from_health(f.status),
            detail=f"{f.area}: {f.detail}",
            automatable=f.status is not HealthStatus.OK and "ruff" in f.area.lower(),
            fix_hint="ruff check --fix src tests" if "ruff" in f.area.lower() else "",
        )
        for f in audit.findings
        if f.status is not HealthStatus.OK
    ]
    status = _from_health(audit.worst_status)
    if not findings:
        findings.append(
            IntegrityFinding(
                domain="code",
                agent="Bob",
                status=IntegritySeverity.OK,
                detail=audit.summary or "Codebase checks passed.",
            )
        )
    return DomainReport(
        domain="code",
        agent="Bob",
        status=status,
        findings=findings,
        summary=audit.summary,
    )


def check_algorithms(repo_root: Path) -> DomainReport:
    """Julie — algorithm mesh modules importable and listed in brain."""
    findings: list[IntegrityFinding] = []
    store = BrainStore.open(repo_root)
    algos = store.algorithms
    if not algos:
        findings.append(
            IntegrityFinding(
                domain="algorithms",
                agent="Julie",
                status=IntegritySeverity.DEGRADED,
                detail="No algorithms registered in brain mesh.",
                automatable=False,
                fix_hint="Restore algorithms block in brain/mesh/index.yaml",
            )
        )
    for algo in algos:
        module = str(algo.get("module") or "").strip()
        if not module:
            continue
        try:
            __import__(module)
        except Exception as exc:  # noqa: BLE001
            findings.append(
                IntegrityFinding(
                    domain="algorithms",
                    agent="Julie",
                    status=IntegritySeverity.CRITICAL,
                    detail=f"{algo.get('id', module)} import failed: {exc}",
                    automatable=False,
                    fix_hint=f"Repair module {module}",
                )
            )
    status = _worst([f.status for f in findings]) if findings else IntegritySeverity.OK
    if not findings:
        findings.append(
            IntegrityFinding(
                domain="algorithms",
                agent="Julie",
                status=IntegritySeverity.OK,
                detail=f"{len(algos)} algorithm mesh entries OK.",
            )
        )
    return DomainReport(
        domain="algorithms",
        agent="Julie",
        status=status,
        findings=findings,
        summary=f"Algorithms: {status.value} ({len(algos)} registered).",
    )


def check_docs(repo_root: Path) -> DomainReport:
    """Hailey — spine docs and companion mesh docs present."""
    findings: list[IntegrityFinding] = []
    required = [
        repo_root / "docs" / "design" / "agentic-task-team-loop.md",
        repo_root / "docs" / "safety.md",
        repo_root / "brain" / "spine" / "ATTL.md",
        repo_root / "brain" / "spine" / "Team-Mesh.md",
        repo_root / "loop-constraints.md",
    ]
    for path in required:
        if not path.is_file():
            findings.append(
                IntegrityFinding(
                    domain="docs",
                    agent="Hailey",
                    status=IntegritySeverity.DEGRADED,
                    detail=f"Missing doc: {path.relative_to(repo_root)}",
                    automatable=False,
                    fix_hint=f"Restore {path.name}",
                )
            )
    status = _worst([f.status for f in findings]) if findings else IntegritySeverity.OK
    if not findings:
        findings.append(
            IntegrityFinding(
                domain="docs",
                agent="Hailey",
                status=IntegritySeverity.OK,
                detail="Spine and safety docs present.",
            )
        )
    return DomainReport(
        domain="docs",
        agent="Hailey",
        status=status,
        findings=findings,
        summary=f"Docs: {status.value}.",
    )


def check_safety(repo_root: Path) -> DomainReport:
    """Andrea — hard safety floor loadable; guards module intact."""
    findings: list[IntegrityFinding] = []
    cs = load_constraints(repo_root)
    if cs.pause_active:
        findings.append(
            IntegrityFinding(
                domain="safety",
                agent="Andrea",
                status=IntegritySeverity.CRITICAL,
                detail="loop-pause-all is active — integrity mesh halted.",
                automatable=False,
            )
        )
    if len(cs.hard_floor) < 4:
        findings.append(
            IntegrityFinding(
                domain="safety",
                agent="Andrea",
                status=IntegritySeverity.DEGRADED,
                detail=f"Hard floor has only {len(cs.hard_floor)} rules (expected ≥4).",
                automatable=False,
                fix_hint="Restore Hard Safety Floor in loop-constraints.md",
            )
        )
    guards = repo_root / "src" / "aoa" / "risk" / "guards.py"
    if not guards.is_file():
        findings.append(
            IntegrityFinding(
                domain="safety",
                agent="Andrea",
                status=IntegritySeverity.CRITICAL,
                detail="risk/guards.py missing — never weaken or remove.",
                automatable=False,
            )
        )
    else:
        text = guards.read_text(encoding="utf-8")
        if "def " not in text:
            findings.append(
                IntegrityFinding(
                    domain="safety",
                    agent="Andrea",
                    status=IntegritySeverity.CRITICAL,
                    detail="risk/guards.py appears emptied.",
                    automatable=False,
                )
            )
    status = _worst([f.status for f in findings]) if findings else IntegritySeverity.OK
    if not findings:
        findings.append(
            IntegrityFinding(
                domain="safety",
                agent="Andrea",
                status=IntegritySeverity.OK,
                detail=f"Hard floor OK ({len(cs.hard_floor)} rules); guards present.",
            )
        )
    return DomainReport(
        domain="safety",
        agent="Andrea",
        status=status,
        findings=findings,
        summary=f"Safety: {status.value}.",
    )


def check_neural_memory(repo_root: Path) -> DomainReport:
    """Nova — brain workspace + plasticity memory integrity."""
    findings: list[IntegrityFinding] = []
    ensure_brain_workspace(repo_root)
    store = BrainStore.open(repo_root)
    if not store.required_paths_ok():
        findings.append(
            IntegrityFinding(
                domain="neural_memory",
                agent="Nova",
                status=IntegritySeverity.CRITICAL,
                detail="brain/ required paths incomplete.",
                automatable=True,
                fix_hint="aoa attl brain sync / ensure_brain_workspace",
            )
        )
    members = store.member_names()
    expected = set(roster_names())
    if set(members) != expected and len(members) != 12:
        findings.append(
            IntegrityFinding(
                domain="neural_memory",
                agent="Nova",
                status=IntegritySeverity.DEGRADED,
                detail=f"Mesh members={len(members)} (expected 12).",
                automatable=False,
                fix_hint="Align brain/mesh/index.yaml with TWELVE_MEMBER_ROSTER",
            )
        )
    # Plasticity file may be absent until first consolidate — degraded, not critical.
    plastic_candidates = [
        repo_root / "data" / "paper" / "plasticity" / "memory.json",
        repo_root / "data" / "paper-dry" / "plasticity" / "memory.json",
    ]
    plastic_ok = False
    for path in plastic_candidates:
        if path.is_file():
            mem = load_memory(path)
            plastic_ok = True
            if mem.cycles_consolidated < 0:
                findings.append(
                    IntegrityFinding(
                        domain="neural_memory",
                        agent="Nova",
                        status=IntegritySeverity.DEGRADED,
                        detail=f"Invalid plasticity cycles at {path.name}.",
                        automatable=True,
                        fix_hint="Reset plasticity memory.json",
                    )
                )
            break
    if not plastic_ok:
        findings.append(
            IntegrityFinding(
                domain="neural_memory",
                agent="Nova",
                status=IntegritySeverity.OK,
                detail="Plasticity memory not yet consolidated (optional until first cycles).",
            )
        )
    status = _worst([f.status for f in findings]) if findings else IntegritySeverity.OK
    # If only the optional plasticity OK note, keep overall OK.
    real = [f for f in findings if f.status is not IntegritySeverity.OK]
    if real:
        status = _worst([f.status for f in real])
    elif not findings:
        findings.append(
            IntegrityFinding(
                domain="neural_memory",
                agent="Nova",
                status=IntegritySeverity.OK,
                detail="Brain mesh and neural memory surfaces healthy.",
            )
        )
        status = IntegritySeverity.OK
    return DomainReport(
        domain="neural_memory",
        agent="Nova",
        status=status,
        findings=findings,
        summary=f"Neural memory: {status.value}; brain members={len(members)}.",
    )


def check_workspaces(repo_root: Path) -> DomainReport:
    """Nova — companion workspace mesh integrity (link/status only, never live)."""
    from aoa.config import Config

    findings: list[IntegrityFinding] = []
    cfg = Config.from_env(load_dotenv=False)
    rows = probe_workspaces(cfg)
    if not rows:
        findings.append(
            IntegrityFinding(
                domain="workspaces",
                agent="Nova",
                status=IntegritySeverity.DEGRADED,
                detail="No companion workspaces registered.",
                automatable=False,
            )
        )
    for row in rows:
        if row.offline_only and not row.never_live:
            findings.append(
                IntegrityFinding(
                    domain="workspaces",
                    agent="Nova",
                    status=IntegritySeverity.CRITICAL,
                    detail=f"{row.id}: offline lane missing never_live=true.",
                    automatable=True,
                    fix_hint="Set never_live on offline companion workspaces",
                )
            )
        # Missing sibling dirs are informational degraded, not critical.
        if not row.present and row.id in {"visualhft", "hftbacktest"}:
            findings.append(
                IntegrityFinding(
                    domain="workspaces",
                    agent="Nova",
                    status=IntegritySeverity.OK,
                    detail=f"{row.id}: sibling not present locally (optional).",
                )
            )
    status = _worst(
        [f.status for f in findings if f.status is not IntegritySeverity.OK]
        or [IntegritySeverity.OK]
    )
    if not any(f.status is not IntegritySeverity.OK for f in findings):
        findings = [
            IntegrityFinding(
                domain="workspaces",
                agent="Nova",
                status=IntegritySeverity.OK,
                detail=f"{len(rows)} companion workspaces probed; never-live mesh OK.",
            )
        ]
        status = IntegritySeverity.OK
    return DomainReport(
        domain="workspaces",
        agent="Nova",
        status=status,
        findings=findings,
        summary=f"Workspaces: {status.value} ({len(rows)} probed).",
    )


def check_cohesion(repo_root: Path) -> DomainReport:
    """Alan — Integrity Ten + twelve-member mesh stay cohesive."""
    from aoa.integrity.roster import INTEGRITY_TEN, integrity_names

    findings: list[IntegrityFinding] = []
    names = integrity_names()
    if len(names) != 10 or len(set(names)) != 10:
        findings.append(
            IntegrityFinding(
                domain="cohesion",
                agent="Alan",
                status=IntegritySeverity.CRITICAL,
                detail=f"Integrity Ten size/uniqueness broken: {names}",
                automatable=False,
            )
        )
    twelve = set(roster_names())
    missing = [n for n in names if n not in twelve]
    if missing:
        findings.append(
            IntegrityFinding(
                domain="cohesion",
                agent="Alan",
                status=IntegritySeverity.CRITICAL,
                detail=f"Integrity agents not in twelve-member roster: {missing}",
                automatable=False,
            )
        )
    if len(TWELVE_MEMBER_ROSTER) != 12:
        findings.append(
            IntegrityFinding(
                domain="cohesion",
                agent="Alan",
                status=IntegritySeverity.CRITICAL,
                detail=f"TWELVE_MEMBER_ROSTER size={len(TWELVE_MEMBER_ROSTER)}",
                automatable=False,
            )
        )
    domains = {m.domain for m in INTEGRITY_TEN}
    required_domains = {
        "code",
        "algorithms",
        "neural_memory",
        "cohesion",
        "safety",
        "fix",
        "notify",
        "approvals",
        "critical",
        "docs",
    }
    if domains != required_domains:
        findings.append(
            IntegrityFinding(
                domain="cohesion",
                agent="Alan",
                status=IntegritySeverity.DEGRADED,
                detail=f"Domain set drift: {sorted(domains)}",
                automatable=False,
            )
        )
    status = _worst([f.status for f in findings]) if findings else IntegritySeverity.OK
    if not findings:
        findings.append(
            IntegrityFinding(
                domain="cohesion",
                agent="Alan",
                status=IntegritySeverity.OK,
                detail="Integrity Ten meshed with twelve-member roster.",
            )
        )
    return DomainReport(
        domain="cohesion",
        agent="Alan",
        status=status,
        findings=findings,
        summary=f"Cohesion: {status.value}.",
    )


def run_all_checks(repo_root: Path | None = None) -> list[DomainReport]:
    root = repo_root or Path.cwd()
    return [
        check_code(root),
        check_algorithms(root),
        check_docs(root),
        check_safety(root),
        check_neural_memory(root),
        check_workspaces(root),
        check_cohesion(root),
    ]
