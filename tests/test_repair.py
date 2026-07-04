"""Tests for the Fable 5 repair loop."""

from __future__ import annotations

from pathlib import Path

from aoa.config import Config
from aoa.repair.discovery import discover_repairs
from aoa.repair.orchestrator import RepairOrchestrator
from aoa.repair.store import RepairStore


def _config(tmp_path: Path, **kwargs) -> Config:
    defaults = dict(
        env="test",
        data_dir=tmp_path / "data",
        journal_path=tmp_path / "journal.jsonl",
        plasticity_path=tmp_path / "plasticity.json",
        workloop_path=tmp_path / "workloop",
        repair_path=tmp_path / "repair",
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
    )
    defaults.update(kwargs)
    return Config(**defaults)


def test_discover_repairs_from_state(tmp_path, monkeypatch):
    state = tmp_path / "STATE.md"
    state.write_text(
        "# Loop State\n\n## High Priority\n\n"
        "- **Flaky test in auth** — CI red on main\n\n"
        "## Watch List\n\n"
        "- **Docs drift** — README outdated\n",
        encoding="utf-8",
    )
    repo = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(
        "aoa.repair.discovery.run_verify",
        lambda _root, **kwargs: {"passed": True, "ruff": {"ok": True}, "pytest": {"ok": True}},
    )
    items = discover_repairs(repo_root=repo, state_path=state)
    titles = {i.title for i in items}
    assert "Flaky test in auth" in titles
    assert "Docs drift" in titles


def test_repair_triage_writes_queue(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    cfg = _config(tmp_path)
    orch = RepairOrchestrator(cfg, repo_root=repo, store=RepairStore(cfg.repair_path))

    monkeypatch.setattr(
        "aoa.repair.orchestrator.discover_repairs",
        lambda **kwargs: [],
    )
    result = orch.triage(sync_state=False)
    assert result.run.status == "completed"
    assert cfg.repair_path.joinpath("queue.json").exists()


def test_repair_orchestrator_sync_state(tmp_path):
    cfg = _config(tmp_path, repair_sync_state=True)
    state_path = tmp_path / "STATE.md"
    orch = RepairOrchestrator(cfg, repo_root=tmp_path, store=RepairStore(cfg.repair_path))

    from aoa.repair.models import RepairItem

    items = [
        RepairItem(
            item_id="abc123",
            title="Ruff failure",
            source="verify",
            severity="critical",
            fixable=True,
            detail="unused import",
        )
    ]
    orch.store.save_queue(items)
    from aoa.repair.orchestrator import _sync_state_md

    _sync_state_md(state_path, items, "run1")
    text = state_path.read_text(encoding="utf-8")
    assert "Ruff failure" in text
    assert "abc123" in text
