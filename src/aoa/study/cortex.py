"""Study cortex — drill, grade, vault sync, usage context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aoa.study.curriculum import KnowledgeCard, all_cards, cards_by_field, get_card
from aoa.study.export import export_corpus_manifest, export_training_jsonl
from aoa.study.mastery import StudyMastery, load_mastery, save_mastery
from aoa.vault.store import VaultNote, write_note


@dataclass
class StudyCortex:
    """Learn (spaced drills) then use (prompt block + LoRA export)."""

    mastery_path: Path
    vault_root: Path | None = None
    mastery: StudyMastery | None = None

    @classmethod
    def from_config(cls, config: Any, *, repo_root: Path | None = None) -> StudyCortex:
        mastery_path = Path(getattr(config, "study_path", "") or "")
        if not mastery_path.parts:
            env = getattr(config, "env", "paper-dry")
            data_dir = Path(getattr(config, "data_dir", Path("data") / env))
            mastery_path = data_dir / "study" / "mastery.json"
        vault_rel = getattr(config, "vault_path", "vault") or "vault"
        root = repo_root or Path.cwd()
        vault_root = Path(vault_rel)
        if not vault_root.is_absolute():
            vault_root = root / vault_root
        return cls(mastery_path=mastery_path, vault_root=vault_root)

    def load(self) -> StudyMastery:
        if self.mastery is None:
            self.mastery = load_mastery(self.mastery_path)
        return self.mastery

    def save(self) -> None:
        mastery = self.load()
        save_mastery(self.mastery_path, mastery)

    def status(self) -> dict[str, Any]:
        mastery = self.load()
        cards = all_cards()
        ids = [c.id for c in cards]
        due = mastery.due_ids(ids)
        mastered = mastery.mastered_ids(ids)
        by_field: dict[str, dict[str, int]] = {}
        for card in cards:
            bucket = by_field.setdefault(card.field, {"total": 0, "mastered": 0, "due": 0})
            bucket["total"] += 1
            if card.id in mastered:
                bucket["mastered"] += 1
            if card.id in due:
                bucket["due"] += 1
        return {
            "mastery_path": str(self.mastery_path),
            "n_cards": len(cards),
            "n_due": len(due),
            "n_mastered": len(mastered),
            "sessions": mastery.sessions,
            "lessons": list(mastery.lessons[:10]),
            "by_field": by_field,
            "updated_at": mastery.updated_at,
            "manifest": export_corpus_manifest(cards),
        }

    def drill(
        self,
        *,
        n: int = 3,
        field: str = "",
        include_answers: bool = False,
    ) -> list[dict[str, Any]]:
        mastery = self.load()
        pool = cards_by_field(field) if field else list(all_cards())
        if not pool:
            return []
        ids = [c.id for c in pool]
        due = set(mastery.due_ids(ids))
        # Prefer due, then lowest mastery, then unseen.
        ranked = sorted(
            pool,
            key=lambda c: (
                0 if c.id in due else 1,
                mastery.cards[c.id].mastery_score() if c.id in mastery.cards else -0.01,
                c.id,
            ),
        )
        selected = ranked[: max(1, n)]
        out: list[dict[str, Any]] = []
        for card in selected:
            row = mastery.cards.get(card.id)
            item: dict[str, Any] = {
                "id": card.id,
                "field": card.field,
                "title": card.title,
                "drill_prompt": card.drill_prompt,
                "bridges": list(card.bridges),
                "due": card.id in due,
                "mastery": row.mastery_score() if row else 0.0,
            }
            if include_answers:
                item["statement"] = card.statement
                item["proof_sketch"] = card.proof_sketch
                item["applications"] = list(card.applications)
                item["aoa_mesh"] = card.aoa_mesh
                item["check_keywords"] = list(card.check_keywords)
            out.append(item)
        return out

    def show(self, card_id: str, *, reveal: bool = True) -> dict[str, Any] | None:
        card = get_card(card_id)
        if card is None:
            return None
        mastery = self.load()
        row = mastery.cards.get(card.id)
        data = card.to_context()
        data["mastery"] = row.mastery_score() if row else 0.0
        data["schedule"] = row.to_context() if row else None
        if not reveal:
            data.pop("proof_sketch", None)
            data.pop("check_keywords", None)
        return data

    def grade(self, card_id: str, passed: bool, *, note: str = "") -> dict[str, Any]:
        if get_card(card_id) is None:
            return {"ok": False, "error": f"unknown card {card_id!r}"}
        mastery = self.load()
        row = mastery.grade(card_id, passed, note=note)
        self.save()
        return {"ok": True, "card_id": card_id, "passed": passed, "schedule": row.to_context()}

    def to_usage_block(self, *, limit: int = 8) -> str:
        mastery = self.load()
        meta = [(c.id, c.title, c.aoa_mesh) for c in all_cards()]
        return mastery.to_usage_block(meta, limit=limit)

    def export_jsonl(
        self,
        path: Path,
        *,
        only_mastered: bool = False,
        threshold: float = 0.6,
    ) -> dict[str, Any]:
        return export_training_jsonl(
            path,
            self.load(),
            only_mastered=only_mastered,
            threshold=threshold,
        )

    def sync_vault(self) -> dict[str, Any]:
        """Write progress + per-card vault notes under vault/study/."""
        if self.vault_root is None:
            return {"ok": False, "error": "vault_root not set"}
        mastery = self.load()
        study_dir = self.vault_root / "study"
        cards_dir = study_dir / "cards"
        cards_dir.mkdir(parents=True, exist_ok=True)
        status = self.status()
        progress = VaultNote(
            path=study_dir / "progress.md",
            frontmatter={
                "type": "study-progress",
                "n_cards": status["n_cards"],
                "n_mastered": status["n_mastered"],
                "n_due": status["n_due"],
                "sessions": status["sessions"],
                "last_session": mastery.updated_at or "",
                "slm_phase": "learn",
            },
            body=(
                "\n# Study cortex progress\n\n"
                "Phase **learn**: spaced drills on DE / physics / economics bridges.\n"
                "Phase **use**: `aoa study usage` injects mastered meshes into the swarm "
                "when `AOA_STUDY_USAGE_ENABLED=true`.\n"
                "Phase **distill**: `aoa study export` writes JSONL for LoRA/sLM via "
                "`aoa.adapt.torch_lora`.\n"
            ),
        )
        write_note(progress)
        written = 1
        for card in all_cards():
            row = mastery.cards.get(card.id)
            note = VaultNote(
                path=cards_dir / f"{card.id}.md",
                frontmatter={
                    "type": "study-card",
                    "card_id": card.id,
                    "field": card.field,
                    "title": card.title,
                    "mastery": round(row.mastery_score(), 4) if row else 0.0,
                    "last_reviewed": row.last_reviewed if row else "",
                    "due_at": row.due_at if row else "",
                    "bridges_count": len(card.bridges),
                },
                body=_card_markdown(card),
            )
            write_note(note)
            written += 1
        return {"ok": True, "notes_written": written, "study_dir": str(study_dir)}


def _card_markdown(card: KnowledgeCard) -> str:
    apps = "\n".join(f"- {a}" for a in card.applications)
    bridges = ", ".join(card.bridges) if card.bridges else "_(none)_"
    return (
        f"\n# {card.title}\n\n"
        f"**Field:** `{card.field}` · **id:** `{card.id}`\n\n"
        f"## Statement\n\n{card.statement}\n\n"
        f"## Proof sketch\n\n{card.proof_sketch}\n\n"
        f"## Applications\n\n{apps}\n\n"
        f"## AOA mesh\n\n{card.aoa_mesh}\n\n"
        f"## Bridges\n\n{bridges}\n\n"
        f"## Drill\n\n{card.drill_prompt}\n"
    )


def combined_memory_context(plasticity_block: str, study_block: str) -> str:
    parts = [p for p in (plasticity_block.strip(), study_block.strip()) if p]
    return "\n\n".join(parts)
