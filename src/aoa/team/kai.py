"""Kai — critical failure sentinel (review only when needed)."""

from __future__ import annotations

from typing import Any

from aoa.agents.base import Agent


class KaiAgent(Agent):
    name = "kai"
    display_name = "Kai"
    role = "Critical Failure Sentinel"

    system_prompt = (
        "You are Kai, the critical failure sentinel. You do NOT review routine "
        "changes. You engage only on critical code flaws, system failures, or "
        "when an explicit report is requested. Be blunt and actionable for Aaron/User."
    )

    def should_review(self, signal: dict[str, Any]) -> bool:
        return bool(signal.get("critical") or signal.get("system_failure") or signal.get("report_requested"))

    def review_if_needed(self, signal: dict[str, Any]) -> dict[str, Any]:
        if not self.should_review(signal):
            return {
                "agent": self.display_name,
                "role": self.role,
                "engaged": False,
                "verdict": "skip",
                "summary": "No critical flaw, system failure, or report request — review skipped.",
            }
        reasons = []
        if signal.get("critical"):
            reasons.append("critical_flaw")
        if signal.get("system_failure"):
            reasons.append("system_failure")
        if signal.get("report_requested"):
            reasons.append("report_requested")
        summary = signal.get("summary") or "; ".join(reasons)
        return {
            "agent": self.display_name,
            "role": self.role,
            "engaged": True,
            "verdict": "report",
            "reasons": reasons,
            "summary": summary,
            "detail": signal.get("detail") or "",
        }
