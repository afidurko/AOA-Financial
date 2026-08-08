"""Tests for vault sync engine."""

from __future__ import annotations

from pathlib import Path

from aoa.config import Config
from aoa.vault.sync import sync_vault_engineering, vault_status


def _write_state(repo: Path, *, l2: bool = False) -> None:
    l2_line = "- **L2:** enabled" if l2 else "- **L2:** disabled"
    repo.joinpath("STATE.md").write_text(
        "\n".join(
            [
                "# Loop State — AOA-Financial",
                "",
                "Last run: 2026-07-08 00:00 UTC (test)",
                "",
                "## High Priority (loop is acting or waiting on human)",
                "",
                "- **Item one** — detail",
                "",
                "## Watch List",
                "",
                "- **Watch one** — detail",
                "- **Watch two** — detail",
                "",
                "## Loop automation",
                "",
                "- **L1:** enabled (report-only daily triage)",
                l2_line,
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_engineering_sync_updates_loop_note(tmp_path: Path):
    repo = tmp_path / "repo"
    vault = repo / "vault" / "loops"
    vault.mkdir(parents=True)
    (repo / "vault" / "_schema.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "vault" / "_schema.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (vault / "engineering.md").write_text(
        "---\ntype: loop-engineering\nlast_run: \"\"\nhigh_priority_count: 0\n"
        "watch_count: 0\nqueue_size: 0\nl1_enabled: false\nl2_enabled: false\n"
        "locked: []\n---\n\n# Engineering\n",
        encoding="utf-8",
    )
    _write_state(repo, l2=True)
    cfg = Config(env="test", vault_path="vault", vault_sync_enabled=True)
    result = sync_vault_engineering(cfg, repo_root=repo, dry_run=False, run_verify=False)
    assert result.notes_updated >= 1
    text = (vault / "engineering.md").read_text(encoding="utf-8")
    assert "high_priority_count: 1" in text or "high_priority_count: 1\n" in text
    assert "watch_count: 2" in text


def test_engineering_sync_dry_run_when_l1(tmp_path: Path):
    repo = tmp_path / "repo"
    vault = repo / "vault" / "loops"
    vault.mkdir(parents=True)
    (repo / "vault" / "_schema.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "vault" / "_schema.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (vault / "engineering.md").write_text(
        "---\ntype: loop-engineering\nlast_run: \"\"\nhigh_priority_count: 0\n"
        "watch_count: 0\nqueue_size: 0\nl1_enabled: false\nl2_enabled: false\n"
        "locked: []\n---\n\n# Engineering\n",
        encoding="utf-8",
    )
    _write_state(repo, l2=False)
    cfg = Config(env="test", vault_path="vault", vault_sync_enabled=True)
    result = sync_vault_engineering(cfg, repo_root=repo, dry_run=None, run_verify=False)
    assert result.dry_run is True
    assert "high_priority_count: 0" in (vault / "engineering.md").read_text(encoding="utf-8")


def test_vault_status_reports_stale(tmp_path: Path):
    repo = tmp_path / "repo"
    vault = repo / "vault" / "loops"
    vault.mkdir(parents=True)
    (repo / "vault" / "_schema.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "vault" / "_schema.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (vault / "engineering.md").write_text(
        "---\ntype: loop-engineering\nlast_run: \"\"\nhigh_priority_count: 0\n"
        "watch_count: 0\nqueue_size: 0\nl1_enabled: false\nl2_enabled: false\n"
        "locked: []\n---\n\n# Engineering\n",
        encoding="utf-8",
    )
    _write_state(repo)
    cfg = Config(env="test", vault_path="vault")
    report = vault_status(cfg, repo_root=repo)
    assert report["stale_count"] >= 1
