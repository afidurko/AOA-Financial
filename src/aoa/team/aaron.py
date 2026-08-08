"""Aaron — CEO who fixes team issues and pushes iPhone alerts when needed."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

from aoa.agents.base import Agent
from aoa.notify.iphone import IPhoneNotification, IPhoneNotifier, NotificationReason
from aoa.team.models import (
    CEOReport,
    DecisionBrief,
    HealthReport,
    HealthStatus,
    TeamMemberStatus,
)
from aoa.team.remediation import RemediationAction, RemediationResult, TeamRemediator

if TYPE_CHECKING:
    from aoa.config import Config
    from aoa.journal.store import Journal

_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_ok": {"type": "boolean"},
        "summary": {"type": "string"},
        "user_notifications": {
            "type": "array",
            "items": {"type": "string"},
        },
        "team_status": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "completed": {"type": "boolean"},
                    "notes": {"type": "string"},
                },
                "required": ["name", "role", "completed", "notes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall_ok", "summary", "user_notifications", "team_status"],
    "additionalProperties": False,
}

_VERIFICATION_CHECKS = frozenset({"configuration"})


class AaronAgent(Agent):
    name = "aaron"
    display_name = "Aaron"
    role = "CEO"

    system_prompt = (
        "You are Aaron, the CEO of a twelve-member autonomous team (Tom, Julie, Morgan, "
        "Hailey, Alan, Andrea, Bob, Alex, Nova, Reed, Kai). You are empowered to fix "
        "issues within your team before escalating. Review Bob's health report, any "
        "remediation actions you already took, and each member's deliverables. "
        "Nova owns the second-brain mesh; Reed runs auto task loops; Kai reviews "
        "only on critical flaws or system failures. Confirm everyone did their job. "
        "Only list user_notifications for issues you could NOT fix yourself or that "
        "require the user's verification (missing credentials, live-trading confirmation, "
        "critical Kai reports). Never suggest email — alerts go to the user's iPhone. "
        "Be direct and actionable."
    )

    def __init__(
        self,
        llm,
        *,
        config: Config | None = None,
        remediator: TeamRemediator | None = None,
        notifier: IPhoneNotifier | None = None,
        journal: Journal | None = None,
    ) -> None:
        super().__init__(llm)
        self.config = config
        self.remediator = remediator
        self.notifier = notifier or (
            IPhoneNotifier(
                custom_app_webhook_url=config.custom_app_webhook_url if config else "",
                custom_app_api_key=config.custom_app_api_key if config else "",
                custom_app_device_id=config.custom_app_device_id if config else "",
                pushover_user_key=config.pushover_user_key if config else "",
                pushover_app_token=config.pushover_app_token if config else "",
                ntfy_topic=config.ntfy_topic if config else "",
                ntfy_server=config.ntfy_server if config else "https://ntfy.sh",
            )
            if config
            else IPhoneNotifier()
        )
        self.journal = journal

    def attempt_health_recovery(
        self,
        health: HealthReport,
        *,
        market_cache_clear: Callable[[], None] | None = None,
    ) -> RemediationResult:
        if self.remediator is None:
            return RemediationResult(health=health)
        result = self.remediator.attempt_health_recovery(
            health,
            market_cache_clear=market_cache_clear,
        )
        if self.journal:
            self.journal.record("team.aaron.remediation", result.to_context())
        return result

    def review(
        self,
        *,
        health: HealthReport,
        tom_done: bool,
        julie_done: bool,
        alan_done: bool,
        decision: DecisionBrief | None,
        tom_count: int = 0,
        julie_count: int = 0,
        hailey_done: bool = True,
        andrea_done: bool = True,
        halted: bool = False,
        halt_reason: str = "",
        remediation: RemediationResult | None = None,
        team_remediation: list[RemediationAction] | None = None,
    ) -> CEOReport:
        fixes = []
        if remediation:
            fixes.extend(a.to_context() for a in remediation.actions)
        if team_remediation:
            fixes.extend(a.to_context() for a in team_remediation)

        iphone_items = _iphone_escalations(
            health=health,
            halted=halted,
            halt_reason=halt_reason,
            remediation=remediation,
        )
        iphone_sent = self._push_iphone_alerts(iphone_items)

        context = {
            "health": health.to_context(),
            "bob_completed": True,
            "tom_completed": tom_done,
            "tom_reports": tom_count,
            "julie_completed": julie_done,
            "julie_reports": julie_count,
            "alan_completed": alan_done,
            "hailey_completed": hailey_done,
            "andrea_completed": andrea_done,
            "decision": decision.to_context() if decision else None,
            "halted": halted,
            "fixes_applied": fixes,
            "iphone_escalations": iphone_items,
        }
        prompt = (
            f"Team cycle context:\n{json.dumps(context, default=str)}\n\n"
            "Review the team and return your CEO report as JSON."
        )
        r = self.llm.structured(self.system_prompt, prompt, _SCHEMA)

        # Merge LLM-identified escalations with deterministic ones; push any new ones.
        llm_escalations = list(r.get("user_notifications") or [])
        new_escalations = [e for e in llm_escalations if e not in iphone_items]
        if new_escalations:
            iphone_sent.extend(self._push_iphone_alerts(new_escalations))

        team_status = [
            TeamMemberStatus(
                name=m["name"],
                role=m["role"],
                completed=bool(m["completed"]),
                notes=m.get("notes", ""),
            )
            for m in r.get("team_status") or []
        ]
        team_status = _ensure_roster(team_status)

        all_notifications = list(dict.fromkeys(iphone_items + llm_escalations))
        overall_ok = bool(r.get("overall_ok", True)) and health.can_proceed and not halted
        return CEOReport(
            team_status=team_status,
            user_notifications=all_notifications,
            fixes_applied=fixes,
            iphone_notifications_sent=list(dict.fromkeys(iphone_sent)),
            overall_ok=overall_ok,
            summary=r.get("summary", ""),
        )

    def _push_iphone_alerts(self, messages: list[str]) -> list[str]:
        if not messages:
            return []
        sent: list[str] = []
        for msg in messages:
            reason = (
                NotificationReason.NEEDS_VERIFICATION
                if _looks_like_verification(msg)
                else NotificationReason.UNFIXABLE
            )
            notification = IPhoneNotification(
                title="AOA — Aaron (CEO)",
                message=msg,
                reason=reason,
            )
            try:
                if self.notifier.configured:
                    channels = self.notifier.send(notification)
                    sent.append(f"{msg} → iPhone ({', '.join(channels)})")
                    if self.journal:
                        self.journal.record(
                            "team.aaron.iphone_push",
                            {"message": msg, "reason": reason.value, "channels": channels},
                        )
                else:
                    sent.append(f"{msg} → iPhone (not configured; logged only)")
                    if self.journal:
                        self.journal.record(
                            "team.aaron.iphone_push",
                            {"message": msg, "reason": reason.value, "channels": []},
                        )
            except Exception as exc:  # noqa: BLE001 — do not block the cycle on push failure
                sent.append(f"{msg} → iPhone delivery failed: {exc}")
                if self.journal:
                    self.journal.record(
                        "team.aaron.iphone_push_error",
                        {"message": msg, "error": str(exc)},
                    )
        return sent


def _iphone_escalations(
    *,
    health: HealthReport,
    halted: bool,
    halt_reason: str,
    remediation: RemediationResult | None,
) -> list[str]:
    """Issues Aaron could not fix — push to iPhone, never email."""
    items: list[str] = []
    fixed_targets = set()
    if remediation:
        fixed_targets = {a.target for a in remediation.actions if a.success}

    if not health.can_proceed or halted:
        for check in health.checks:
            if check.status is not HealthStatus.CRITICAL:
                continue
            target = f"Bob/{check.name}"
            if target in fixed_targets and check.auto_fixed:
                continue
            if check.name in _VERIFICATION_CHECKS:
                items.append(
                    f"[Needs your verification] {check.detail} "
                    "Update .env and confirm before the swarm can run."
                )
            else:
                items.append(f"[Bob/{check.name}] {check.detail}")
        if halted and halt_reason and halt_reason not in items:
            items.append(halt_reason)
    return list(dict.fromkeys(items))


def _looks_like_verification(message: str) -> bool:
    lower = message.lower()
    return (
        "verification" in lower
        or "confirm" in lower
        or "credential" in lower
        or "api_key" in lower
        or ".env" in lower
    )


def _ensure_roster(status: list[TeamMemberStatus]) -> list[TeamMemberStatus]:
    from aoa.team.roster import roster_pairs

    roster = roster_pairs()
    by_name = {m.name: m for m in status}
    out: list[TeamMemberStatus] = []
    for name, role in roster:
        if name in by_name:
            out.append(by_name[name])
        else:
            out.append(TeamMemberStatus(name=name, role=role, completed=False, notes="Not reported."))
    return out
