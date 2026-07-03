"""Distill journal events into durable plastic memory."""

from __future__ import annotations

from collections import Counter
from typing import Any

from aoa.journal.store import Journal
from aoa.plasticity.memory import PlasticMemory, touch_memory

_TRUST_DECAY = 0.95
_VETO_PENALTY = 0.12
_GUARD_PENALTY = 0.08
_APPROVAL_BONUS = 0.05
_MAX_TRUST = 1.0
_MIN_TRUST = -1.0
_TRUST_EPSILON = 0.01


def consolidate(
    journal: Journal,
    memory: PlasticMemory,
    *,
    tail: int = 200,
    max_lessons: int = 10,
) -> PlasticMemory:
    """Scan recent journal entries and update plastic memory in place."""
    entries = journal.tail(tail)
    llm_vetoes: Counter[tuple[str, str]] = Counter()
    guard_rejections: Counter[str] = Counter()
    approved_symbols: set[str] = set()

    for entry in entries:
        event = entry.get("event", "")
        if event == "risk.review":
            _scan_risk_review(entry, llm_vetoes, guard_rejections, approved_symbols)
        elif event in {"order.submitted", "order.dry_run"}:
            sym = str(entry.get("symbol", "")).upper()
            if sym:
                approved_symbols.add(sym)

    _decay_symbol_trust(memory)
    _apply_trust_updates(memory, llm_vetoes, guard_rejections, approved_symbols)

    lessons = _build_lessons(llm_vetoes, guard_rejections, max_lessons=max_lessons)
    memory.lessons = _merge_lessons(memory.lessons, lessons, max_lessons=max_lessons)
    memory.veto_counts = {
        sym: count for sym, count in _symbol_veto_totals(llm_vetoes, guard_rejections).items()
    }
    memory.cycles_consolidated += 1
    touch_memory(memory)
    return memory


def _scan_risk_review(
    entry: dict[str, Any],
    llm_vetoes: Counter[tuple[str, str]],
    guard_rejections: Counter[str],
    approved_symbols: set[str],
) -> None:
    for prop in entry.get("proposals", []):
        sym = str(prop.get("symbol", "")).upper()
        if not sym:
            continue
        if prop.get("approved"):
            approved_symbols.add(sym)
            continue
        for note in prop.get("risk_notes", []):
            text = str(note)
            if text.startswith("LLM veto:"):
                llm_vetoes[(sym, text)] += 1
            else:
                guard_rejections[sym] += 1


def _decay_symbol_trust(memory: PlasticMemory) -> None:
    stale: list[str] = []
    for sym, score in memory.symbol_trust.items():
        decayed = score * _TRUST_DECAY
        if abs(decayed) < _TRUST_EPSILON:
            stale.append(sym)
        else:
            memory.symbol_trust[sym] = decayed
    for sym in stale:
        del memory.symbol_trust[sym]


def _apply_trust_updates(
    memory: PlasticMemory,
    llm_vetoes: Counter[tuple[str, str]],
    guard_rejections: Counter[str],
    approved_symbols: set[str],
) -> None:
    for (sym, _), count in llm_vetoes.items():
        current = memory.symbol_trust.get(sym, 0.0)
        memory.symbol_trust[sym] = _clamp_trust(current - _VETO_PENALTY * count)

    for sym, count in guard_rejections.items():
        current = memory.symbol_trust.get(sym, 0.0)
        memory.symbol_trust[sym] = _clamp_trust(current - _GUARD_PENALTY * count)

    for sym in approved_symbols:
        current = memory.symbol_trust.get(sym, 0.0)
        memory.symbol_trust[sym] = _clamp_trust(current + _APPROVAL_BONUS)


def _clamp_trust(score: float) -> float:
    return max(_MIN_TRUST, min(_MAX_TRUST, score))


def _symbol_veto_totals(
    llm_vetoes: Counter[tuple[str, str]],
    guard_rejections: Counter[str],
) -> Counter[str]:
    totals: Counter[str] = Counter()
    for (sym, _), count in llm_vetoes.items():
        totals[sym] += count
    totals.update(guard_rejections)
    return totals


def _build_lessons(
    llm_vetoes: Counter[tuple[str, str]],
    guard_rejections: Counter[str],
    *,
    max_lessons: int,
) -> list[str]:
    lessons: list[str] = []

    for (sym, reason), count in llm_vetoes.most_common(5):
        detail = reason.removeprefix("LLM veto: ").strip()
        if count >= 2:
            lessons.append(f"{sym} was LLM-vetoed {count}x recently: {detail}")
        else:
            lessons.append(f"{sym} LLM veto: {detail}")

    for sym, count in guard_rejections.most_common(3):
        if count >= 2:
            lessons.append(
                f"{sym} failed deterministic guards {count}x recently — "
                "size more conservatively or skip conflicting setups"
            )
        elif count == 1:
            lessons.append(f"{sym} was blocked by deterministic guards once recently")

    return lessons[:max_lessons]


def _merge_lessons(existing: list[str], fresh: list[str], *, max_lessons: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for lesson in fresh + existing:
        if lesson in seen:
            continue
        seen.add(lesson)
        merged.append(lesson)
        if len(merged) >= max_lessons:
            break
    return merged
