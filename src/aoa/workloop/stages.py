"""Work-loop pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aoa.workloop.adapt import write_adaptations
from aoa.workloop.approval import ApprovalRequired, check_approval
from aoa.workloop.discover import discover_sources
from aoa.workloop.execute import execute_changes
from aoa.workloop.extract import extract_insights
from aoa.workloop.merge import run_merge
from aoa.workloop.models import STAGE_ORDER, WorkloopRun
from aoa.workloop.propose import build_proposal
from aoa.workloop.store import WorkloopStore
from aoa.workloop.upgrade import run_upgrade
from aoa.workloop.verify import run_verify


@dataclass
class WorkloopContext:
    config: object
    store: WorkloopStore
    run: WorkloopRun
    repo_root: Path
    dry_run: bool = False


class WorkloopStage:
    name: str = "stage"

    def run(self, ctx: WorkloopContext) -> bool:
        raise NotImplementedError


class DiscoverStage(WorkloopStage):
    name = "discover"

    def run(self, ctx: WorkloopContext) -> bool:
        sources = discover_sources(ctx.config, ctx.repo_root)
        ctx.run.discovered = [s.to_context() for s in sources]
        ctx.run.notes.append(f"Discovered {len(sources)} learning source(s).")
        ctx.store.record("workloop.discover", {"count": len(sources)})
        return True


class ExtractStage(WorkloopStage):
    name = "extract"

    def run(self, ctx: WorkloopContext) -> bool:
        from aoa.workloop.models import LearningSource

        sources = [
            LearningSource(
                kind=s["kind"],
                path=s["path"],
                summary=s.get("summary", ""),
                metadata=s.get("metadata", {}),
            )
            for s in ctx.run.discovered
        ]
        ctx.run.extracted = extract_insights(
            sources,
            journal_path=ctx.config.journal_path,
            plasticity_path=ctx.config.plasticity_path,
            journal_tail=ctx.config.workloop_journal_tail,
        )
        ctx.store.record("workloop.extract", {"keys": sorted(ctx.run.extracted.keys())})
        return True


class AdaptStage(WorkloopStage):
    name = "adapt"

    def run(self, ctx: WorkloopContext) -> bool:
        ctx.run.adaptations = write_adaptations(
            ctx.store,
            ctx.run.extracted,
            max_lessons=ctx.config.workloop_max_lessons,
        )
        ctx.store.record("workloop.adapt", {"count": len(ctx.run.adaptations)})
        return True


class ProposeStage(WorkloopStage):
    name = "propose"

    def run(self, ctx: WorkloopContext) -> bool:
        ctx.run.proposal = build_proposal(ctx.repo_root)
        ctx.store.record("workloop.propose", {"has_changes": ctx.run.proposal.get("has_changes")})
        return True


class ApprovalStage(WorkloopStage):
    name = "approval"

    def run(self, ctx: WorkloopContext) -> bool:
        if ctx.dry_run:
            ctx.run.approval = {
                "approver": ctx.config.workloop_approver,
                "note": "dry-run approval bypass",
            }
            ctx.run.notes.append("Dry-run: approval gate bypassed.")
            return True
        try:
            ctx.run.approval = check_approval(
                ctx.store,
                run_id=ctx.run.run_id,
                approver=ctx.config.workloop_approver,
            )
            ctx.run.notes.append(f"Approved by {ctx.run.approval.get('approver')}.")
            return True
        except ApprovalRequired as exc:
            ctx.run.status = "awaiting_approval"
            ctx.run.error = str(exc)
            ctx.run.notes.append(str(exc))
            ctx.store.record("workloop.awaiting_approval", {"run_id": ctx.run.run_id})
            return False


class ExecuteStage(WorkloopStage):
    name = "execute"

    def run(self, ctx: WorkloopContext) -> bool:
        if ctx.dry_run:
            ctx.run.execution = {"message": "Dry-run: execute skipped."}
            return True
        ctx.run.execution = execute_changes(
            ctx.run.proposal,
            repo_root=ctx.repo_root,
            auto_commit=ctx.config.workloop_auto_commit,
        )
        ctx.store.record("workloop.execute", ctx.run.execution)
        return True


class VerifyStage(WorkloopStage):
    name = "verify"

    def run(self, ctx: WorkloopContext) -> bool:
        ctx.run.verify = run_verify(ctx.repo_root)
        ctx.store.record("workloop.verify", {"passed": ctx.run.verify.get("passed")})
        if not ctx.run.verify.get("passed"):
            ctx.run.status = "failed"
            ctx.run.error = "Initial verification failed."
            return False
        return True


class UpgradeStage(WorkloopStage):
    name = "upgrade"

    def run(self, ctx: WorkloopContext) -> bool:
        if ctx.dry_run:
            ctx.run.upgrade = {"ok": True, "message": "Dry-run: upgrade skipped."}
            return True
        ctx.run.upgrade = run_upgrade(ctx.repo_root)
        ctx.store.record("workloop.upgrade", {"ok": ctx.run.upgrade.get("ok")})
        if not ctx.run.upgrade.get("ok"):
            ctx.run.status = "failed"
            ctx.run.error = "Dependency upgrade failed."
            return False
        return True


class ReverifyStage(WorkloopStage):
    name = "reverify"

    def run(self, ctx: WorkloopContext) -> bool:
        ctx.run.reverify = run_verify(ctx.repo_root)
        ctx.store.record("workloop.reverify", {"passed": ctx.run.reverify.get("passed")})
        if not ctx.run.reverify.get("passed"):
            ctx.run.status = "failed"
            ctx.run.error = "Post-upgrade verification failed."
            return False
        return True


class MergeStage(WorkloopStage):
    name = "merge"

    def run(self, ctx: WorkloopContext) -> bool:
        if ctx.dry_run:
            ctx.run.merge = {"message": "Dry-run: merge skipped."}
            ctx.run.status = "completed"
            return True
        ctx.run.merge = run_merge(
            ctx.run.proposal,
            repo_root=ctx.repo_root,
            base_branch=ctx.config.workloop_base_branch,
            allow_merge=ctx.config.workloop_allow_merge,
        )
        ctx.store.record("workloop.merge", ctx.run.merge)
        ctx.run.status = "completed"
        ctx.store.clear_approval()
        return True


def default_stages() -> list[WorkloopStage]:
    return [
        DiscoverStage(),
        ExtractStage(),
        AdaptStage(),
        ProposeStage(),
        ApprovalStage(),
        ExecuteStage(),
        VerifyStage(),
        UpgradeStage(),
        ReverifyStage(),
        MergeStage(),
    ]


def stage_index(name: str) -> int:
    try:
        return STAGE_ORDER.index(name)
    except ValueError as exc:
        raise ValueError(f"Unknown work-loop stage: {name!r}") from exc
