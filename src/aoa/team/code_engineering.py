"""Deterministic code-health checks for Julie, Alan, and Bob.

These checks encode the coding-engineer playbook: one source of truth for shared
helpers, no module singletons in the web layer, and a healthy import graph.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from aoa.team.models import HealthStatus


@dataclass
class CodeFinding:
    area: str
    status: HealthStatus
    detail: str

    def to_context(self) -> dict:
        return {
            "area": self.area,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass
class CodeQualityReport:
    """Outcome of Bob/Julie's code engineering sweep."""

    findings: list[CodeFinding] = field(default_factory=list)
    can_proceed: bool = True
    summary: str = ""

    @property
    def worst_status(self) -> HealthStatus:
        order = {HealthStatus.OK: 0, HealthStatus.DEGRADED: 1, HealthStatus.CRITICAL: 2}
        worst = HealthStatus.OK
        for finding in self.findings:
            if order[finding.status] > order[worst]:
                worst = finding.status
        return worst

    def to_context(self) -> dict:
        return {
            "can_proceed": self.can_proceed,
            "summary": self.summary,
            "worst_status": self.worst_status.value,
            "findings": [f.to_context() for f in self.findings],
        }


def run_code_quality_audit(*, repo_root: Path | None = None) -> CodeQualityReport:
    """Run the coding-engineer checklist (deterministic, no LLM)."""
    root = repo_root or _find_repo_root()
    findings = [
        _check_shared_pricing_module(root),
        _check_shared_brokerage_constants(root),
        _check_web_app_state_pattern(root),
        _check_pipeline_helpers(root),
        _check_ruff_if_available(root),
    ]
    critical = any(f.status is HealthStatus.CRITICAL for f in findings)
    degraded = any(f.status is HealthStatus.DEGRADED for f in findings)
    if critical:
        summary = "Critical code-quality issues — halt until fixed."
    elif degraded:
        summary = "Code quality degraded — proceed with caution."
    else:
        summary = "Codebase checks passed."
    return CodeQualityReport(
        findings=findings,
        can_proceed=not critical,
        summary=summary,
    )


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "aoa").exists():
            return parent
    return Path.cwd()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _check_shared_pricing_module(root: Path) -> CodeFinding:
    pricing = root / "src" / "aoa" / "execution" / "pricing.py"
    stages = _read(root / "src" / "aoa" / "swarm" / "stages.py")
    orchestrator = _read(root / "src" / "aoa" / "swarm" / "orchestrator.py")
    if not pricing.exists():
        return CodeFinding("pricing", HealthStatus.CRITICAL, "Missing execution/pricing.py.")
    if "def _marketable_limit" in stages or "def _marketable_limit" in orchestrator:
        return CodeFinding(
            "pricing",
            HealthStatus.DEGRADED,
            "Duplicate _marketable_limit helpers still present.",
        )
    if "marketable_limit" not in stages:
        return CodeFinding(
            "pricing",
            HealthStatus.DEGRADED,
            "Stages should import marketable_limit from execution.pricing.",
        )
    return CodeFinding(
        "pricing",
        HealthStatus.OK,
        "Order pricing centralized in execution/pricing.py.",
    )


def _check_shared_brokerage_constants(root: Path) -> CodeFinding:
    constants = root / "src" / "aoa" / "brokerage" / "constants.py"
    alpaca = _read(root / "src" / "aoa" / "brokerage" / "alpaca.py")
    if not constants.exists():
        return CodeFinding(
            "brokerage_constants",
            HealthStatus.DEGRADED,
            "Missing brokerage/constants.py.",
        )
    if "_VALID_DATA_FEEDS = frozenset" in alpaca:
        return CodeFinding(
            "brokerage_constants",
            HealthStatus.DEGRADED,
            "Alpaca feed constants duplicated in alpaca.py.",
        )
    return CodeFinding(
        "brokerage_constants",
        HealthStatus.OK,
        "Alpaca validation constants centralized.",
    )


def _check_web_app_state_pattern(root: Path) -> CodeFinding:
    app_py = _read(root / "src" / "aoa" / "web" / "app.py")
    if "_app:" in app_py or "_runner:" in app_py:
        return CodeFinding(
            "web_app",
            HealthStatus.DEGRADED,
            "Web app still uses module-level singleton globals.",
        )
    if "app.state" not in app_py:
        return CodeFinding(
            "web_app",
            HealthStatus.DEGRADED,
            "Web app should store orchestrator/runner on app.state.",
        )
    return CodeFinding(
        "web_app",
        HealthStatus.OK,
        "Web app uses FastAPI app.state (no module singleton).",
    )


def _check_pipeline_helpers(root: Path) -> CodeFinding:
    pipeline = _read(root / "src" / "aoa" / "swarm" / "pipeline.py")
    stages = _read(root / "src" / "aoa" / "swarm" / "stages.py")
    if "def run_from" not in pipeline:
        return CodeFinding(
            "pipeline",
            HealthStatus.DEGRADED,
            "Pipeline missing run_from() for team mid-cycle injection.",
        )
    if "_pm_raw" in stages:
        return CodeFinding(
            "pipeline",
            HealthStatus.DEGRADED,
            "Materialize still reads _pm_raw from environment global context.",
        )
    if "portfolio_output" not in stages:
        return CodeFinding(
            "pipeline",
            HealthStatus.DEGRADED,
            "Portfolio output should live on CycleContext.portfolio_output.",
        )
    return CodeFinding(
        "pipeline",
        HealthStatus.OK,
        "Pipeline handoffs use explicit context fields.",
    )


def _check_ruff_if_available(root: Path) -> CodeFinding:
    try:
        import ruff  # noqa: F401
    except ImportError:
        return CodeFinding(
            "ruff",
            HealthStatus.OK,
            "Ruff not installed in this runtime — skipped.",
        )
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src", "tests"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stdout or proc.stderr or "ruff check failed").strip()
        return CodeFinding("ruff", HealthStatus.CRITICAL, detail[:500])
    return CodeFinding("ruff", HealthStatus.OK, "ruff check src tests passed.")


def import_sweep(modules: tuple[str, ...]) -> CodeFinding:
    failed: list[str] = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{mod}: {exc}")
    if failed:
        return CodeFinding(
            "imports",
            HealthStatus.CRITICAL,
            "Import failures: " + "; ".join(failed),
        )
    return CodeFinding(
        "imports",
        HealthStatus.OK,
        f"{len(modules)} core modules import cleanly.",
    )
