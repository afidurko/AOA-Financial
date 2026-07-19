"""Spaced mastery state for the study cortex (plasticity analogue)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@dataclass
class CardMastery:
    """SM-2-lite schedule for one card."""

    ease: float = 2.3
    interval_days: float = 0.0
    reps: int = 0
    lapses: int = 0
    last_result: str = ""  # ok | miss | ""
    last_reviewed: str = ""
    due_at: str = ""
    note: str = ""

    def to_context(self) -> dict[str, Any]:
        return {
            "ease": self.ease,
            "interval_days": self.interval_days,
            "reps": self.reps,
            "lapses": self.lapses,
            "last_result": self.last_result,
            "last_reviewed": self.last_reviewed,
            "due_at": self.due_at,
            "note": self.note,
        }

    @classmethod
    def from_context(cls, data: dict[str, Any]) -> CardMastery:
        return cls(
            ease=float(data.get("ease", 2.3) or 2.3),
            interval_days=float(data.get("interval_days", 0) or 0),
            reps=int(data.get("reps", 0) or 0),
            lapses=int(data.get("lapses", 0) or 0),
            last_result=str(data.get("last_result", "")),
            last_reviewed=str(data.get("last_reviewed", "")),
            due_at=str(data.get("due_at", "")),
            note=str(data.get("note", "")),
        )

    def is_due(self, now: datetime | None = None) -> bool:
        if not self.due_at:
            return True
        now = now or _utc_now()
        try:
            due = datetime.fromisoformat(self.due_at)
        except ValueError:
            return True
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return now >= due

    def mastery_score(self) -> float:
        """Rough 0..1 competence from reps/lapses/ease."""
        if self.reps == 0 and self.lapses == 0:
            return 0.0
        base = min(1.0, self.reps / 5.0)
        penalty = min(0.6, self.lapses * 0.15)
        ease_bonus = max(0.0, min(0.2, (self.ease - 2.0) * 0.1))
        return max(0.0, min(1.0, base - penalty + ease_bonus))


@dataclass
class StudyMastery:
    """Durable study memory — lessons + per-card schedules."""

    cards: dict[str, CardMastery] = field(default_factory=dict)
    lessons: list[str] = field(default_factory=list)
    sessions: int = 0
    updated_at: str = ""

    def to_context(self) -> dict[str, Any]:
        return {
            "cards": {cid: m.to_context() for cid, m in self.cards.items()},
            "lessons": list(self.lessons),
            "sessions": self.sessions,
            "updated_at": self.updated_at,
        }

    def ensure(self, card_id: str) -> CardMastery:
        if card_id not in self.cards:
            self.cards[card_id] = CardMastery()
        return self.cards[card_id]

    def grade(self, card_id: str, passed: bool, *, note: str = "") -> CardMastery:
        """Update spaced schedule after a drill attempt."""
        row = self.ensure(card_id)
        now = _utc_now()
        row.last_reviewed = _iso(now)
        row.last_result = "ok" if passed else "miss"
        if note:
            row.note = note[:240]
        if passed:
            row.reps += 1
            if row.reps == 1:
                row.interval_days = 1.0
            elif row.reps == 2:
                row.interval_days = 3.0
            else:
                row.interval_days = max(1.0, row.interval_days * row.ease)
            row.ease = min(3.0, row.ease + 0.05)
        else:
            row.lapses += 1
            row.reps = max(0, row.reps - 1)
            row.interval_days = 0.5
            row.ease = max(1.3, row.ease - 0.2)
            lesson = f"{card_id}: missed drill"
            if note:
                lesson += f" — {note[:120]}"
            self.lessons = [lesson, *[x for x in self.lessons if x != lesson]][:40]
        row.due_at = _iso(now + timedelta(days=row.interval_days))
        self.sessions += 1
        self.updated_at = _iso(now)
        return row

    def due_ids(self, card_ids: list[str], *, now: datetime | None = None) -> list[str]:
        now = now or _utc_now()
        due: list[str] = []
        for cid in card_ids:
            row = self.cards.get(cid)
            if row is None or row.is_due(now):
                due.append(cid)
        return due

    def mastered_ids(self, card_ids: list[str], *, threshold: float = 0.6) -> list[str]:
        out: list[str] = []
        for cid in card_ids:
            row = self.cards.get(cid)
            if row and row.mastery_score() >= threshold:
                out.append(cid)
        return out

    def to_usage_block(
        self,
        cards_meta: list[tuple[str, str, str, str]],
        *,
        limit: int = 8,
        baseline: bool = True,
    ) -> str:
        """Render standing + mastered meshes for swarm / tutor usage.

        ``cards_meta`` is a list of (id, title, aoa_mesh, field).
        When ``baseline`` is true, all bridge-field meshes are always included
        so swarm injection stays active before any drills are graded.
        """
        baseline_rows: list[tuple[str, str, str]] = []
        scored: list[tuple[float, str, str, str]] = []
        for cid, title, mesh, card_field in cards_meta:
            if not mesh:
                continue
            row = self.cards.get(cid)
            score = row.mastery_score() if row else 0.0
            if baseline and card_field == "bridge":
                baseline_rows.append((cid, title, mesh))
            if score >= 0.45:
                scored.append((score, cid, title, mesh))
        scored.sort(reverse=True)

        # Prefer mastered non-baseline cards to fill remaining slots.
        baseline_ids = {cid for cid, _, _ in baseline_rows}
        mastered_extra = [(s, c, t, m) for s, c, t, m in scored if c not in baseline_ids]

        if not baseline_rows and not mastered_extra:
            return ""

        lines = ["Study cortex (always-on theory → usage constraints):"]
        slots = max(1, limit)
        for cid, title, mesh in baseline_rows[:slots]:
            row = self.cards.get(cid)
            score = row.mastery_score() if row else 0.0
            tag = f"mastery {score:.2f}" if score > 0 else "baseline"
            lines.append(f"- [{cid}] {title} ({tag}): {mesh}")
            slots -= 1
        for score, cid, title, mesh in mastered_extra[: max(0, slots)]:
            lines.append(f"- [{cid}] {title} (mastery {score:.2f}): {mesh}")
        if self.lessons:
            lines.append("Recent study lessons (weak spots):")
            for lesson in self.lessons[:5]:
                lines.append(f"- {lesson}")
        return "\n".join(lines)


def load_mastery(path: Path) -> StudyMastery:
    if not path.exists():
        return StudyMastery()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return StudyMastery()
    cards = {
        str(k): CardMastery.from_context(v if isinstance(v, dict) else {})
        for k, v in (data.get("cards") or {}).items()
    }
    return StudyMastery(
        cards=cards,
        lessons=[str(x) for x in data.get("lessons", [])],
        sessions=int(data.get("sessions", 0) or 0),
        updated_at=str(data.get("updated_at", "")),
    )


def save_mastery(path: Path, mastery: StudyMastery) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mastery.to_context(), indent=2), encoding="utf-8")
