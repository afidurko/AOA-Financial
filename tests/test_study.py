"""Tests for the study cortex (learn → use → distill)."""

from __future__ import annotations

import json
from pathlib import Path

from aoa.study.cortex import StudyCortex, combined_memory_context
from aoa.study.curriculum import all_cards, get_card
from aoa.study.export import export_training_jsonl
from aoa.study.mastery import StudyMastery, load_mastery, save_mastery
from aoa.swarm.stages import _cycle_memory_context


def test_curriculum_has_all_fields_and_bridges():
    cards = all_cards()
    assert len(cards) >= 12
    fields = {c.field for c in cards}
    assert {"de", "physics", "econ", "bridge"} <= fields
    # Every bridge id referenced should resolve.
    for card in cards:
        for bid in card.bridges:
            assert get_card(bid) is not None, f"{card.id} → missing {bid}"


def test_mastery_grade_schedules_and_lessons(tmp_path: Path):
    path = tmp_path / "mastery.json"
    mastery = StudyMastery()
    mastery.grade("de-picard", True)
    mastery.grade("de-picard", True)
    row = mastery.cards["de-picard"]
    assert row.reps == 2
    assert row.interval_days >= 1.0
    assert not row.is_due()  # just scheduled out

    mastery.grade("bridge-bs-heat", False, note="forgot heat kernel")
    assert mastery.lessons
    assert "bridge-bs-heat" in mastery.lessons[0]
    save_mastery(path, mastery)
    reloaded = load_mastery(path)
    assert reloaded.cards["de-picard"].reps == 2
    assert reloaded.sessions == 3


def test_cortex_drill_grade_usage_export_sync(tmp_path: Path):
    mastery_path = tmp_path / "study" / "mastery.json"
    vault_root = tmp_path / "vault"
    cortex = StudyCortex(mastery_path=mastery_path, vault_root=vault_root)

    drills = cortex.drill(n=2, include_answers=False)
    assert len(drills) == 2
    assert "proof_sketch" not in drills[0]

    card_id = drills[0]["id"]
    # Pump mastery high enough for usage block.
    for _ in range(4):
        cortex.grade(card_id, True)
    # Also grade a bridge with mesh content explicitly if needed.
    bridge = get_card("bridge-ou-meanrev")
    assert bridge is not None
    for _ in range(4):
        cortex.grade(bridge.id, True)

    usage = cortex.to_usage_block()
    assert "Study cortex" in usage
    assert bridge.id in usage or card_id in usage

    out = tmp_path / "corpus.jsonl"
    summary = cortex.export_jsonl(out, only_mastered=True)
    assert summary["written"] >= 1
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    row = json.loads(lines[0])
    assert "instruction" in row and "response" in row

    sync = cortex.sync_vault()
    assert sync["ok"]
    assert (vault_root / "study" / "progress.md").is_file()
    assert (vault_root / "study" / "cards" / f"{card_id}.md").is_file()


def test_combined_memory_context_and_cycle_helper():
    assert combined_memory_context("a", "") == "a"
    assert combined_memory_context("", "b") == "b"
    assert "a" in combined_memory_context("a", "b") and "b" in combined_memory_context("a", "b")

    class _Cfg:
        study_usage_enabled = False
        study_usage_limit = 8

    class _Ctx:
        config = _Cfg()
        plasticity = None

    assert _cycle_memory_context(_Ctx()) == ""


def test_export_all_cards(tmp_path: Path):
    path = tmp_path / "all.jsonl"
    summary = export_training_jsonl(path, StudyMastery(), only_mastered=False)
    assert summary["written"] == len(all_cards())
