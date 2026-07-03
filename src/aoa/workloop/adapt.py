"""Write learning adaptations from extracted insights."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aoa.workloop.store import WorkloopStore


def write_adaptations(
    store: WorkloopStore,
    extracted: dict[str, Any],
    *,
    max_lessons: int = 20,
) -> list[dict[str, Any]]:
    learnings = store.load_learnings()
    lessons: list[str] = list(learnings.get("lessons", []))
    adaptations: list[dict[str, Any]] = list(learnings.get("adaptations", []))

    new_lessons = _lessons_from_extracted(extracted)
    merged = _merge_unique(lessons, new_lessons, max_lessons)
    learnings["lessons"] = merged

    adaptation = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source_kinds": extracted.get("source_kinds", []),
        "journal_events": extracted.get("journal_events", {}),
        "actions": _recommended_actions(extracted),
    }
    adaptations.append(adaptation)
    learnings["adaptations"] = adaptations[-max_lessons:]
    store.save_learnings(learnings)

    return [adaptation]


def _lessons_from_extracted(extracted: dict[str, Any]) -> list[str]:
    lessons: list[str] = []

    for lesson in extracted.get("plasticity_lessons", []):
        lessons.append(f"Plasticity: {lesson}")

    for lesson in extracted.get("workloop_lessons", [])[:5]:
        lessons.append(f"Prior work-loop: {lesson}")

    if extracted.get("previous_run_id"):
        lessons.append(
            f"Chained from prior run {extracted['previous_run_id']} "
            f"(iteration {extracted.get('prior_iterations', 0)})."
        )

    for veto in extracted.get("recent_vetoes", [])[:5]:
        sym = veto.get("symbol", "")
        note = veto.get("note", "")
        lessons.append(f"Risk pattern on {sym}: {note}")

    events = extracted.get("journal_events", {})
    if events.get("broker.error", 0) >= 2:
        lessons.append(
            "Broker errors are recurring — review connectivity, credentials, and feed settings."
        )
    if events.get("plasticity.update", 0) == 0:
        lessons.append("Plasticity memory has not been updated recently — confirm loop health.")

    commits = extracted.get("git_commits", [])
    if commits:
        lessons.append(f"Recent repo activity: {commits[0]}")

    return lessons


def _recommended_actions(extracted: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    events = extracted.get("journal_events", {})
    if events.get("order.error", 0) > 0:
        actions.append("Harden order submission error handling and retries.")
    if extracted.get("recent_vetoes"):
        actions.append("Tune portfolio sizing to reduce repeat LLM vetoes.")
    if extracted.get("test_files", 0) < 5:
        actions.append("Expand automated test coverage for changed modules.")
    if not actions:
        actions.append("Continue incremental improvements; no urgent adaptation flagged.")
    return actions


def _merge_unique(existing: list[str], fresh: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for lesson in fresh + existing:
        if lesson in seen:
            continue
        seen.add(lesson)
        merged.append(lesson)
        if len(merged) >= limit:
            break
    return merged
