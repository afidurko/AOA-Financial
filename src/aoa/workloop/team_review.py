"""Five-member team review of proposed work-loop changes before implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aoa.config import Config
from aoa.notify.iphone import IPhoneNotification, IPhoneNotifier, NotificationReason
from aoa.team.code_engineering import CodeQualityReport, run_code_quality_audit

_SENSITIVE_FRAGMENTS = (
    ".env",
    "credentials",
    "secret",
    "deploy/",
    ".pem",
    "id_rsa",
)

_ALAN_CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {
            "type": "string",
            "enum": ["approve", "reject", "escalate_user"],
        },
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
        "risks": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["recommendation", "summary", "confidence", "risks"],
    "additionalProperties": False,
}

_AARON_CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["approve", "reject", "escalate_user"],
        },
        "required_approver": {"type": "string"},
        "summary": {"type": "string"},
        "user_notifications": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["verdict", "required_approver", "summary", "user_notifications"],
    "additionalProperties": False,
}


def review_change_proposal(
    *,
    proposal: dict[str, Any],
    adaptations: list[dict[str, Any]],
    repo_root: Path,
    config: Config,
    run_id: str,
    llm=None,
) -> dict[str, Any]:
    """Bob + Julie (deterministic) and Alan + Aaron (LLM or rules) review a change set."""
    bob = run_code_quality_audit(repo_root=repo_root)
    julie = _julie_review(proposal, config=config)
    alan = _alan_review(
        bob=bob,
        julie=julie,
        proposal=proposal,
        adaptations=adaptations,
        llm=llm,
        config=config,
    )
    aaron = _aaron_decide(
        bob=bob,
        julie=julie,
        alan=alan,
        proposal=proposal,
        config=config,
        run_id=run_id,
        llm=llm,
    )
    return {
        "run_id": run_id,
        "bob": bob.to_context(),
        "julie": julie,
        "alan": alan,
        "aaron": aaron,
        "verdict": aaron["verdict"],
        "required_approver": aaron["required_approver"],
        "escalation_messages": aaron.get("user_notifications", []),
        "summary": aaron["summary"],
    }


def push_escalation_alerts(config: Config, messages: list[str], *, run_id: str) -> list[str]:
    """Deliver Aaron CEO escalations to the user's iPhone when configured."""
    if not messages:
        return []
    notifier = IPhoneNotifier(
        custom_app_webhook_url=config.custom_app_webhook_url,
        custom_app_api_key=config.custom_app_api_key,
        custom_app_device_id=config.custom_app_device_id,
        pushover_user_key=config.pushover_user_key,
        pushover_app_token=config.pushover_app_token,
        ntfy_topic=config.ntfy_topic,
        ntfy_server=config.ntfy_server,
    )
    sent: list[str] = []
    for msg in messages:
        notification = IPhoneNotification(
            title="AOA — Work-loop change review",
            message=msg,
            reason=NotificationReason.NEEDS_VERIFICATION,
        )
        try:
            if notifier.configured:
                channels = notifier.send(notification)
                sent.append(f"{msg} → iPhone ({', '.join(channels)})")
            else:
                sent.append(f"{msg} → iPhone (not configured; logged only)")
        except Exception as exc:  # noqa: BLE001
            sent.append(f"{msg} → iPhone delivery failed: {exc}")
    return sent


def _julie_review(proposal: dict[str, Any], *, config: Config) -> dict[str, Any]:
    changed = list(proposal.get("changed_files") or [])
    sensitive = [f for f in changed if _is_sensitive_path(f)]
    n = len(changed)
    threshold = config.workloop_escalation_file_threshold
    flags: list[str] = []
    if sensitive:
        flags.append(f"sensitive paths: {', '.join(sensitive[:3])}")
    if n >= threshold:
        flags.append(f"{n} files changed (threshold {threshold})")
    if not proposal.get("has_changes"):
        flags.append("no uncommitted changes")

    status = "ok"
    if sensitive or n >= threshold:
        status = "escalate"
    elif not proposal.get("has_changes"):
        status = "noop"

    return {
        "agent": "Julie",
        "role": "Algorithm Specialist & Code Clarity",
        "status": status,
        "changed_files": n,
        "sensitive_paths": sensitive,
        "flags": flags,
        "summary": (
            "Routine change scope."
            if status == "ok"
            else "Change scope needs elevated review."
            if status == "escalate"
            else "No implementation diff in working tree."
        ),
    }


def _alan_review(
    *,
    bob: CodeQualityReport,
    julie: dict[str, Any],
    proposal: dict[str, Any],
    adaptations: list[dict[str, Any]],
    llm,
    config: Config,
) -> dict[str, Any]:
    actions = _collect_recommended_actions(adaptations)
    prompt = (
        f"Change proposal:\n{json.dumps(proposal, default=str)}\n\n"
        f"Bob code-quality:\n{json.dumps(bob.to_context(), default=str)}\n\n"
        f"Julie scope review:\n{json.dumps(julie, default=str)}\n\n"
        f"Recommended adaptations:\n{json.dumps(actions, default=str)}\n\n"
        "Recommend approve (routine), reject (unsafe), or escalate_user (user must confirm)."
    )
    if llm is not None and config.anthropic_api_key:
        try:
            raw = llm.structured(
                (
                    "You are Alan, code oversight on an autonomous trading team. "
                    "Review a proposed repo change before implementation. "
                    "Reject if Bob reports critical issues. Escalate to the human user "
                    "for sensitive paths, large diffs, or live-trading/config risk."
                ),
                prompt,
                _ALAN_CHANGE_SCHEMA,
            )
            return {
                "agent": "Alan",
                "role": "Decision Aggregator & Code Oversight",
                "recommendation": raw["recommendation"],
                "summary": raw["summary"],
                "confidence": float(raw.get("confidence", 0.5)),
                "risks": list(raw.get("risks") or []),
                "source": "llm",
            }
        except Exception as exc:  # noqa: BLE001
            fallback = _alan_rules(bob, julie, proposal, actions)
            fallback["llm_error"] = str(exc)
            return fallback
    return _alan_rules(bob, julie, proposal, actions)


def _alan_rules(
    bob: CodeQualityReport,
    julie: dict[str, Any],
    proposal: dict[str, Any],
    actions: list[str],
) -> dict[str, Any]:
    risks: list[str] = []
    if not bob.can_proceed:
        risks.append(bob.summary)
    if julie.get("status") == "escalate":
        risks.extend(julie.get("flags") or [])
    if _actions_need_escalation(actions):
        risks.append("high-impact adaptation actions recommended")

    if not bob.can_proceed:
        rec = "reject"
    elif julie.get("status") == "escalate" or _actions_need_escalation(actions):
        rec = "escalate_user"
    elif not proposal.get("has_changes"):
        rec = "approve"
    else:
        rec = "approve"

    return {
        "agent": "Alan",
        "role": "Decision Aggregator & Code Oversight",
        "recommendation": rec,
        "summary": "Deterministic change brief from Bob and Julie inputs.",
        "confidence": 0.7 if rec == "approve" else 0.9,
        "risks": risks,
        "source": "rules",
    }


def _aaron_decide(
    *,
    bob: CodeQualityReport,
    julie: dict[str, Any],
    alan: dict[str, Any],
    proposal: dict[str, Any],
    config: Config,
    run_id: str,
    llm,
) -> dict[str, Any]:
    prompt = (
        f"Work-loop run {run_id}.\n"
        f"Proposal:\n{json.dumps(proposal, default=str)}\n\n"
        f"Alan recommendation:\n{json.dumps(alan, default=str)}\n\n"
        f"Julie:\n{json.dumps(julie, default=str)}\n\n"
        f"Bob:\n{json.dumps(bob.to_context(), default=str)}\n\n"
        "As CEO, set verdict (approve/reject/escalate_user) and required_approver "
        f"({config.workloop_approver!r} for routine team approval, "
        f"{config.workloop_user_approver!r} when the human user must confirm). "
        "Populate user_notifications only when escalating or rejecting."
    )
    if llm is not None and config.anthropic_api_key:
        try:
            raw = llm.structured(
                (
                    "You are Aaron, CEO of the autonomous trading team. "
                    "Gate work-loop code changes before implementation. "
                    "Approve routine fixes yourself; escalate config, secrets, large "
                    "or risky changes to the user. Never suggest email — iPhone alerts only."
                ),
                prompt,
                _AARON_CHANGE_SCHEMA,
            )
            return {
                "agent": "Aaron",
                "role": "CEO",
                "verdict": raw["verdict"],
                "required_approver": raw["required_approver"],
                "summary": raw["summary"],
                "user_notifications": list(raw.get("user_notifications") or []),
                "source": "llm",
            }
        except Exception as exc:  # noqa: BLE001
            fallback = _aaron_rules(alan, bob, julie, proposal, config, run_id)
            fallback["llm_error"] = str(exc)
            return fallback
    return _aaron_rules(alan, bob, julie, proposal, config, run_id)


def _aaron_rules(
    alan: dict[str, Any],
    bob: CodeQualityReport,
    julie: dict[str, Any],
    proposal: dict[str, Any],
    config: Config,
    run_id: str,
) -> dict[str, Any]:
    rec = alan.get("recommendation", "approve")
    notifications: list[str] = []

    if rec == "reject":
        verdict = "reject"
        required = config.workloop_approver
        summary = f"Team rejected run {run_id}: {alan.get('summary', 'unsafe change')}."
        notifications.append(summary)
    elif rec == "escalate_user":
        verdict = "escalate_user"
        required = config.workloop_user_approver
        summary = (
            f"Run {run_id} escalated to user: "
            f"{proposal.get('summary', 'change requires human confirmation')}."
        )
        notifications.append(
            f"[Needs your verification] {summary} "
            f"Approve with: aoa workloop approve --approver {required}"
        )
    elif not proposal.get("has_changes"):
        verdict = "approve"
        required = config.workloop_approver
        summary = f"Run {run_id}: no repo diff — team cleared for bookkeeping."
    else:
        verdict = "approve"
        required = config.workloop_approver
        summary = (
            f"Run {run_id}: routine change approved by team "
            f"({proposal.get('summary', '')})."
        )

    if not bob.can_proceed:
        verdict = "reject"
        required = config.workloop_approver
        summary = f"Run {run_id} blocked: {bob.summary}"
        notifications = [summary]

    return {
        "agent": "Aaron",
        "role": "CEO",
        "verdict": verdict,
        "required_approver": required,
        "summary": summary,
        "user_notifications": notifications,
        "source": "rules",
    }


def _collect_recommended_actions(adaptations: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in adaptations:
        for action in item.get("actions") or []:
            if action and action not in actions:
                actions.append(str(action))
    return actions


def _actions_need_escalation(actions: list[str]) -> bool:
    risky = ("live", "credential", "secret", "merge", "deploy", "production")
    blob = " ".join(actions).lower()
    return any(token in blob for token in risky)


def _is_sensitive_path(path: str) -> bool:
    lowered = path.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_FRAGMENTS)
