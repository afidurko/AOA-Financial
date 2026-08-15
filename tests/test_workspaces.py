"""Tests for companion workspace mesh."""

from __future__ import annotations

import json

from aoa.cli import cmd_workspaces_status, main
from aoa.config import Config
from aoa.workspaces import probe_workspaces, workspaces_report


def test_workspaces_report_shape(monkeypatch):
    monkeypatch.delenv("AOA_OPENSTOCK_URL", raising=False)
    monkeypatch.delenv("AOA_QM_URL", raising=False)
    monkeypatch.delenv("AOA_VISUALHFT_URL", raising=False)
    cfg = Config.from_env(load_dotenv=False)
    report = workspaces_report(cfg)
    assert report["count"] == 4
    assert report["never_live"] is True
    ids = {w["id"] for w in report["workspaces"]}
    assert ids == {"openstock", "qm", "visualhft", "hftbacktest"}
    vh = next(w for w in report["workspaces"] if w["id"] == "visualhft")
    assert vh["docs"].endswith("visualhft-integration.md")
    assert vh["detail"]["python_lane"]["offline_only"] is True


def test_workspaces_respects_visualhft_url(monkeypatch):
    monkeypatch.setenv("AOA_VISUALHFT_URL", "https://example.test/vh")
    cfg = Config.from_env(load_dotenv=False)
    assert cfg.visualhft_url == "https://example.test/vh"
    rows = probe_workspaces(cfg)
    vh = next(w for w in rows if w.id == "visualhft")
    assert vh.linked is True
    assert vh.url == "https://example.test/vh"


def test_cmd_workspaces_status_json(capsys, monkeypatch):
    monkeypatch.setenv("AOA_OPENSTOCK_URL", "http://localhost:3000")
    code = cmd_workspaces_status(as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["linked"] >= 1
    os_row = next(w for w in data["workspaces"] if w["id"] == "openstock")
    assert os_row["linked"] is True
    assert os_row["url"] == "http://localhost:3000"


def test_cli_workspaces_skips_env_template(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("AOA_ENV=paper\n", encoding="utf-8")
    code = main(["workspaces", "status", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["count"] == 4
    assert not (tmp_path / ".env").exists()
