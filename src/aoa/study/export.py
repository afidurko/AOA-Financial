"""Export mastered cards as JSONL for future LoRA / sLM fine-tuning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aoa.study.curriculum import KnowledgeCard, all_cards
from aoa.study.mastery import StudyMastery


def export_training_jsonl(
    path: Path,
    mastery: StudyMastery,
    *,
    min_mastery: float = 0.0,
    only_mastered: bool = False,
    threshold: float = 0.6,
) -> dict[str, Any]:
    """Write instruction/response pairs. Returns a small summary dict."""
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    with path.open("w", encoding="utf-8") as fh:
        for card in all_cards():
            row = mastery.cards.get(card.id)
            score = row.mastery_score() if row else 0.0
            if only_mastered and score < threshold:
                skipped += 1
                continue
            if score < min_mastery:
                skipped += 1
                continue
            pair = card.training_pair()
            pair["mastery"] = round(score, 4)
            fh.write(json.dumps(pair, ensure_ascii=False) + "\n")
            written += 1
    return {"path": str(path), "written": written, "skipped": skipped}


def export_corpus_manifest(cards: tuple[KnowledgeCard, ...] | None = None) -> dict[str, Any]:
    cards = cards or all_cards()
    by_field: dict[str, int] = {}
    for card in cards:
        by_field[card.field] = by_field.get(card.field, 0) + 1
    return {
        "n_cards": len(cards),
        "by_field": by_field,
        "lora_hint": (
            "Fine-tune with aoa.adapt.torch_lora on a small base instruct model; "
            "train only LoRA adapters on this JSONL, then merge for tutoring usage."
        ),
    }
