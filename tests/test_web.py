"""Tests for the FastAPI web dashboard and REST API."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from aoa.config import Config, RiskLimits  # noqa: E402
from aoa.web.app import create_app  # noqa: E402


@pytest.fixture
def client(fake_broker, fake_llm, monkeypatch, tmp_path):
    cfg = Config(
        anthropic_api_key="x",
        alpaca_key_id="x",
        alpaca_secret_key="x",
        universe=("AAPL",),
        dry_run=True,
        news_enabled=False,
        web_auto_loop=False,
        journal_path=tmp_path / "j.jsonl",
        risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )

    monkeypatch.setattr("aoa.cli.build_broker", lambda c: fake_broker)
    monkeypatch.setattr("aoa.cli.build_llm", lambda c: fake_llm)
    monkeypatch.setattr("aoa.cli.build_news", lambda c: __import__(
        "aoa.data.news", fromlist=["NullNewsFeed"]
    ).NullNewsFeed())

    with TestClient(create_app(cfg)) as tc:
        yield tc


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dashboard_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "AOA Financial" in r.text


def test_api_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["account"]["equity"] == 100_000.0
    assert "loop" in data


def test_api_run_cycle(client):
    r = client.post("/api/run")
    assert r.status_code == 200
    data = r.json()
    assert "proposals" in data
    assert data.get("health") is not None
    assert data["health"]["can_proceed"] is True
    assert "ceo" in data


def test_api_config_team_mode(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["team_mode"] is True


def test_api_journal(client):
    client.post("/api/run")
    r = client.get("/api/journal?n=5")
    assert r.status_code == 200
    assert len(r.json()["entries"]) > 0
