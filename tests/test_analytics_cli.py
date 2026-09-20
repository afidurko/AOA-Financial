"""``aoa analytics`` terminal views."""

from __future__ import annotations

import json

from aoa.analytics.report import VIEWS, run_analytics_view
from aoa.analytics.store import AnalyticsStore
from aoa.cli import main


def _seed(path) -> None:
    store = AnalyticsStore(path)
    for run_id, start, end, price in (
        ("r1", "2026-07-01T10:00:00+00:00", "2026-07-01T10:00:30+00:00", 100.0),
        ("r2", "2026-07-01T11:00:00+00:00", "2026-07-01T11:00:20+00:00", 105.0),
    ):
        store.record_cycle(
            run_id=run_id, started_at=start, completed_at=end, mode="dry-run",
            halted=False, halt_reason="", payload={},
        )
        store.insert_prices(run_id, {"AAPL": price})
        store.insert_signals(
            run_id, [{"ticker": "AAPL", "agent": "Tom", "direction": "up", "conviction": 0.8}]
        )
        store.insert_stage_metric(run_id, "analyze", 1200.0)
    store.insert_proposals(
        "r1", [{"symbol": "AAPL", "side": "buy", "approved": True, "strategy": "long_equity",
                "est_notional": 5000}]
    )
    store.close()


def test_missing_database_is_reported(tmp_path, capsys):
    assert run_analytics_view(tmp_path / "none.sqlite", "summary") == 1
    assert "No analytics database" in capsys.readouterr().out


def test_every_view_renders_text_and_json(tmp_path, capsys):
    db = tmp_path / "a.sqlite"
    _seed(db)
    for view in VIEWS:
        assert run_analytics_view(db, view) == 0
        text = capsys.readouterr().out
        assert f"Analytics ({view})" in text
        assert run_analytics_view(db, view, as_json=True) == 0
        json.loads(capsys.readouterr().out)

    run_analytics_view(db, "summary")
    out = capsys.readouterr().out
    assert "Tom" in out and "100%" in out  # 100→105 with an "up" call = one hit
    assert "analyze" in out and "long_equity" in out
    assert "Cycles: 2" in out


def test_cli_wires_analytics_command(tmp_path, monkeypatch, capsys):
    db = tmp_path / "a.sqlite"
    _seed(db)
    monkeypatch.setenv("AOA_ANALYTICS_DB_PATH", str(db))
    monkeypatch.setattr("aoa.cli._ensure_env_template", lambda: None)
    assert main(["analytics", "agents", "--json", "--runs", "50"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["agent"] == "Tom" and rows[0]["hit_rate"] == 1.0
