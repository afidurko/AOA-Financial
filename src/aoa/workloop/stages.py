"""Work-loop pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aoa.workloop.adapt import write_adaptations
from aoa.workloop.approval import (
    ApprovalRequired,
    TeamRejected,
    check_approval,
    check_team_review_gate,
    required_approver_for_run,
)
from aoa.workloop.discover import discover_sources
from aoa.workloop.execute import execute_changes
from aoa.workloop.extract import extract_insights
from aoa.workloop.merge import run_merge
from aoa.workloop.models import STAGE_ORDER, WorkloopRun
from aoa.workloop.propose import build_proposal
from aoa.workloop.store import WorkloopStore
from aoa.workloop.team_review import push_escalation_alerts, review_change_proposal
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
            workloop_path=ctx.config.workloop_path,
            journal_tail=ctx.config.workloop_journal_tail,
            previous_run_id=ctx.run.previous_run_id,
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


class VaultSyncStage(WorkloopStage):
    """Refresh loop/system vault notes from workloop insights."""

    name = "vault_sync"

    def run(self, ctx: WorkloopContext) -> bool:
        from aoa.vault.sync import sync_vault_from_workloop

        if not ctx.config.vault_sync_enabled:
            ctx.run.notes.append("Vault sync disabled.")
            return True
        dry_run = not ctx.config.vault_auto_write
        result = sync_vault_from_workloop(
            ctx.config,
            repo_root=ctx.repo_root,
            extracted=ctx.run.extracted,
            dry_run=dry_run,
        )
        ctx.store.record(
            "workloop.vault_sync",
            {
                "dry_run": result.dry_run,
                "notes_updated": result.notes_updated,
                "properties_changed": result.properties_changed,
            },
        )
        ctx.run.notes.append(
            f"Vault sync: updated {result.notes_updated} note(s), "
            f"{result.properties_changed} propert(ies)."
        )
        return True


class ProposeStage(WorkloopStage):
    name = "propose"

    def run(self, ctx: WorkloopContext) -> bool:
        ctx.run.proposal = build_proposal(ctx.repo_root)
        ctx.store.record("workloop.propose", {"has_changes": ctx.run.proposal.get("has_changes")})
        return True


class TeamReviewStage(WorkloopStage):
    """Bob, Julie, Alan, and Aaron review proposed changes before sign-off."""

    name = "team_review"

    def run(self, ctx: WorkloopContext) -> bool:
        if not ctx.config.workloop_team_review_enabled:
            ctx.run.notes.append("Team review disabled (AOA_WORKLOOP_TEAM_REVIEW_ENABLED=false).")
            return True
        if ctx.dry_run:
            ctx.run.team_review = {
                "verdict": "approve",
                "required_approver": ctx.config.workloop_approver,
                "summary": "Dry-run team review bypass.",
            }
            ctx.run.notes.append("Dry-run: team review bypassed.")
            return True

        llm = _optional_llm(ctx.config)
        review = review_change_proposal(
            proposal=ctx.run.proposal,
            adaptations=ctx.run.adaptations,
            repo_root=ctx.repo_root,
            config=ctx.config,
            run_id=ctx.run.run_id,
            llm=llm,
        )
        ctx.run.team_review = review
        ctx.store.record(
            "workloop.team_review",
            {
                "run_id": ctx.run.run_id,
                "verdict": review.get("verdict"),
                "required_approver": review.get("required_approver"),
            },
        )
        ctx.run.notes.append(f"Team review: {review.get('summary', '')}")

        try:
            check_team_review_gate(review)
        except TeamRejected as exc:
            ctx.run.status = "rejected_by_team"
            ctx.run.error = str(exc)
            ctx.run.notes.append(str(exc))
            return False

        if review.get("verdict") == "escalate_user":
            alerts = push_escalation_alerts(
                ctx.config,
                list(review.get("escalation_messages") or []),
                run_id=ctx.run.run_id,
            )
            for alert in alerts:
                ctx.run.notes.append(alert)
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

        approver = required_approver_for_run(ctx.run, ctx.config)
        if (
            not ctx.run.proposal.get("has_changes")
            and (ctx.run.team_review or {}).get("verdict") == "approve"
        ):
            ctx.run.approval = {
                "approver": approver,
                "approved_at": "",
                "note": "auto-approved: no repo changes after team review",
            }
            ctx.run.notes.append(f"Auto-approved by team ({approver}): no diff to implement.")
            return True

        try:
            ctx.run.approval = check_approval(
                ctx.store,
                run_id=ctx.run.run_id,
                approver=approver,
            )
            ctx.run.notes.append(f"Approved by {ctx.run.approval.get('approver')}.")
            return True
        except ApprovalRequired as exc:
            ctx.run.status = "awaiting_approval"
            ctx.run.error = str(exc)
            ctx.run.notes.append(str(exc))
            ctx.store.record(
                "workloop.awaiting_approval",
                {
                    "run_id": ctx.run.run_id,
                    "required_approver": approver,
                },
            )
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
        VaultSyncStage(),
        ProposeStage(),
        TeamReviewStage(),
        ApprovalStage(),
        ExecuteStage(),
        VerifyStage(),
        UpgradeStage(),
        ReverifyStage(),
        MergeStage(),
    ]


def _optional_llm(config):
    if not config.anthropic_api_key:
        return None
    try:
        from aoa.llm.client import LLMClient

        return LLMClient(
            config.anthropic_api_key,
            model=config.model,
            effort=config.effort,
        )
    except Exception:  # noqa: BLE001
        return None


def stage_index(name: str) -> int:
    try:
        return STAGE_ORDER.index(name)
    except ValueError as exc:
        raise ValueError(f"Unknown work-loop stage: {name!r}") from exc
