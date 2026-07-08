"""Tests for vault note store."""

from __future__ import annotations

from pathlib import Path

from aoa.vault.store import apply_property_updates, read_note, write_note


def test_frontmatter_round_trip(tmp_path: Path):
    path = tmp_path / "note.md"
    path.write_text(
        "---\ntype: loop-engineering\nlast_run: old\nlocked: []\n---\n\n# Body\n",
        encoding="utf-8",
    )
    note = read_note(path)
    assert note.note_type == "loop-engineering"
    assert note.body.strip() == "# Body"
    note.frontmatter["last_run"] = "new"
    write_note(note)
    reread = read_note(path)
    assert reread.frontmatter["last_run"] == "new"
    assert reread.body.strip() == "# Body"


def test_locked_properties_preserved(tmp_path: Path):
    path = tmp_path / "note.md"
    path.write_text(
        "---\ntype: symbol\nticker: AAPL\nlocked:\n  - ticker\n---\n",
        encoding="utf-8",
    )
    note = read_note(path)
    changed = apply_property_updates(note, {"ticker": "MSFT", "direction": "long"})
    assert "ticker" not in changed
    assert "direction" in changed
    assert note.frontmatter["ticker"] == "AAPL"
    assert note.frontmatter["direction"] == "long"
