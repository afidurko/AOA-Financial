"""Pine generator, desk sub-team cycle, webhook gate, web routes and CLI (all offline)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from aoa.cli import main
from aoa.tradingview.desk import DESK_MEMBERS, DeskRunner
from aoa.tradingview.memory import DeskMemory
from aoa.tradingview.pine import _f, generate_pine, lint_pine, pine_filename
from aoa.tradingview.presets import PRESETS, get_preset, list_presets
from aoa.tradingview.webhook import (
    WebhookError,
    handle_alert,
    load_alerts,
    parse_alert,
    respond_alert,
    verify_token,
)


@pytest.fixture
def desk_env(tmp_path, monkeypatch):
    """Isolate every desk artefact (memory, alerts, caches, reports) under tmp_path."""
    monkeypatch.setenv("AOA_TRADINGVIEW_MEMORY_PATH", str(tmp_path / "memory.json"))
    monkeypatch.setenv("AOA_TRADINGVIEW_ALERTS_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.delenv("AOA_TRADINGVIEW_WEBHOOK_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- #
# presets
# --------------------------------------------------------------------------- #


def test_preset_catalogue_covers_every_horizon_and_market() -> None:
    horizons = {p.horizon for p in PRESETS.values()}
    assert horizons == {"hft", "scalp", "intraday", "swing", "position"}
    assert {p.market for p in PRESETS.values()} == {"crypto", "equity"}
    tfs = {p.timeframe for p in PRESETS.values()}
    assert {"1S", "1", "5", "15", "60", "240", "1D", "1W"} <= tfs
    for p in PRESETS.values():
        d = p.to_dict()
        assert d["name"] == p.name and d["timeframe_label"]
        if p.market == "equity":
            assert not p.allow_short, "equity presets are long-only by design"
        if p.horizon in ("hft", "scalp") and p.market == "equity":
            assert p.risk.session, "intraday equity presets must be session-bound"
        assert p.tunable, "every preset needs a walk-forward grid"
        for k in p.tunable:
            assert k in p.params
    assert {p.name for p in list_presets(horizon="hft")} == {n for n in PRESETS if n.startswith("hft")}
    assert all(p.market == "crypto" for p in list_presets(market="crypto"))
    with pytest.raises(KeyError):
        get_preset("nope")
    assert get_preset("scalp-crypto-1m-momentum").with_timeframe("5m").timeframe == "5"


# --------------------------------------------------------------------------- #
# pine
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_generated_pine_lints_and_contains_contract(name: str) -> None:
    preset = get_preset(name)
    src = generate_pine(preset)
    assert lint_pine(src) == []
    assert src.startswith("//@version=6")
    assert f'strategy("AOA {preset.name}"' in src
    assert "process_orders_on_close=false" in src
    assert "strategy.percent_of_equity" in src
    assert f"default_qty_value={preset.risk.qty_pct_equity:g}" in src
    assert f"commission_value={preset.costs.commission_pct:g}" in src
    assert '"source": "aoa-tradingview"' in src and f'"preset": "{preset.name}"' in src
    assert "alert_message=" in src
    assert "strategy.entry(" in src and "strategy.exit(" in src
    assert f'allowShort = input.bool({"true" if preset.allow_short else "false"}, "Allow shorts"' in src
    assert 'strategy.entry("S", strategy.short' in src  # always guarded by allowShort
    if preset.risk.session:
        assert f'sessInput  = input.session("{preset.risk.session}"' in src
        assert "syminfo.timezone" in src and "lastSessionBar = useSession" in src
    if preset.fundamentals.enabled:
        assert "request.financial(" in src
    if preset.tf.is_seconds:
        assert "Premium" in src
    for key, value in preset.params.items():
        if isinstance(value, bool):
            literal = f"input.bool({'true' if value else 'false'}"
        elif isinstance(value, int):
            literal = f"input.int({value},"
        else:
            literal = f"input.float({_f(value)},"
        assert literal in src, f"param {key}={value!r} not surfaced as an input default"
    assert f"atrLen     = input.int({preset.params.get('atr_len', 14)}," in src
    assert pine_filename(preset) == f"{preset.name}.pine"


def test_lint_pine_catches_structural_problems() -> None:
    good = generate_pine(get_preset("swing-equity-1d-trend"))
    assert lint_pine(good) == []
    assert "missing //@version=6 pragma" in lint_pine(good.replace("//@version=6", "//@version=5"))
    assert any("unterminated" in p for p in lint_pine(good + '\nx = "oops\n'))
    assert any("unbalanced" in p for p in lint_pine(good + "\ny = ta.sma(close, 3\n"))
    assert any("strategy()" in p for p in lint_pine(good + '\nstrategy("again")\n'))


# --------------------------------------------------------------------------- #
# desk
# --------------------------------------------------------------------------- #


def test_desk_run_synthetic_end_to_end(desk_env: Path) -> None:
    runner = DeskRunner(
        source="synthetic",
        report_dir=desk_env / "reports",
        cache_dir=desk_env / "cache",
        folds=2,
        monte_carlo=True,
        use_fundamentals=False,
    )
    report = runner.run(
        ["AAPL", "BTC-USD"],
        presets=["swing-equity-1d-trend", "position-crypto-1d-trend", "swing-equity-1d-breakout"],
        limit=700,
        seed=3,
        export_pine=True,
        capture=False,
    )
    assert report.never_live is True
    assert {r.market for r in report.rows} == {"equity", "crypto"}
    assert all(not r.error for r in report.rows), [r.error for r in report.rows]
    equity_rows = [r for r in report.rows if r.symbol == "AAPL"]
    assert {r.preset for r in equity_rows} == {"swing-equity-1d-trend", "swing-equity-1d-breakout"}
    for r in report.rows:
        assert r.metrics["total_trades"] >= 0 and r.walk_forward is not None
        assert r.monte_carlo is not None and "ok" in r.monte_carlo
        assert -1.0 <= r.reward <= 1.0
    assert len(report.proposals) == 2  # one per symbol
    for p in report.proposals:
        assert p["requires_human"] is True and p["action"] in ("enter_long", "enter_short", "hold", "reduce", "exit")
    assert len(report.pine_files) == 3 and all(Path(f).is_file() for f in report.pine_files)
    assert (desk_env / "reports" / "latest.json").is_file()
    latest = json.loads((desk_env / "reports" / "latest.json").read_text())
    assert latest["lead"] == "Julie" and len(latest["members"]) == len(DESK_MEMBERS)
    assert latest["never_live"] is True
    assert any("no broker calls" in n for n in report.notes)
    # memory persisted with synapses for every row plus the connectome state
    mem = DeskMemory.load()
    assert len(mem.synapses) == len(report.rows)
    assert mem.connectome["steps"] == 2 and mem.consolidations == 1
    assert {"Dara", "Piper", "Quinn", "Mira", "Sol", "Julie"} <= set(mem.agents)
    assert mem.episodes[-1]["kind"] == "desk.run"
    lines = report.summary_lines()
    assert lines[0].startswith("TradingView desk run") and any("motor→" in ln for ln in lines)


def test_desk_flags_insufficient_bars_and_reuses_memory(desk_env: Path) -> None:
    runner = DeskRunner(source="synthetic", report_dir=desk_env / "reports", use_fundamentals=False, folds=0, monte_carlo=False)
    report = runner.run(["MSFT"], presets=["position-equity-1d-fundamental"], limit=100, seed=1, capture=False)
    assert len(report.rows) == 1 and report.rows[0].error.startswith("insufficient bars")
    assert report.proposals == []
    # second cycle sees the first cycle's memory and increments consolidations
    runner2 = DeskRunner(source="synthetic", report_dir=desk_env / "reports", use_fundamentals=False, folds=0, monte_carlo=False)
    runner2.run(["MSFT"], presets=["swing-equity-1d-trend"], limit=600, seed=1, capture=False)
    assert DeskMemory.load().consolidations == 2


def test_desk_fundamentals_gate_zeroes_reward(desk_env: Path, monkeypatch) -> None:
    from aoa.tradingview.fundamentals import FundamentalSnapshot

    class FakeFeed:
        def get(self, symbol, *, refresh=False):
            return FundamentalSnapshot(symbol, trailing_pe=900.0)

    runner = DeskRunner(source="yahoo", report_dir=desk_env / "reports", folds=0, monte_carlo=False, fundamentals=FakeFeed())
    monkeypatch.setattr(runner, "fetch", lambda symbol, tf, limit=None, seed=None: (__import__("aoa.tradingview.data", fromlist=["synthetic_bars"]).synthetic_bars(symbol, get_preset("position-equity-1d-fundamental").tf, n=700, seed=2), "yahoo"))
    report = runner.run(["AAPL"], presets=["position-equity-1d-fundamental"], capture=False)
    row = report.rows[0]
    assert row.fundamentals_ok is False and "trailing P/E" in row.error
    assert row.reward <= 0.0 and row.fundamentals["trailing_pe"] == 900.0


# --------------------------------------------------------------------------- #
# webhook
# --------------------------------------------------------------------------- #


def _alert(**over) -> dict:
    base = {
        "source": "aoa-tradingview",
        "preset": "swing-equity-1d-trend",
        "event": "enter_long",
        "market": "equity",
        "ticker": "aapl",
        "exchange": "NASDAQ",
        "tf": "D",
        "price": "191.25",
        "time": 1700000000000,
    }
    base.update(over)
    return base


def test_parse_alert_validation() -> None:
    assert parse_alert(json.dumps(_alert()))["ticker"] == "aapl"
    with pytest.raises(WebhookError):
        parse_alert("not json")
    with pytest.raises(WebhookError):
        parse_alert("[1,2]")
    with pytest.raises(WebhookError):
        parse_alert(_alert(source="other"))
    with pytest.raises(WebhookError):
        parse_alert(_alert(event="buy"))
    with pytest.raises(WebhookError):
        parse_alert(_alert(ticker=""))


def test_verify_token(monkeypatch) -> None:
    monkeypatch.delenv("AOA_TRADINGVIEW_WEBHOOK_SECRET", raising=False)
    verify_token({}, None)  # no secret configured → open
    monkeypatch.setenv("AOA_TRADINGVIEW_WEBHOOK_SECRET", "s3cret")
    verify_token({}, "s3cret")
    verify_token({"token": "s3cret"}, None)
    with pytest.raises(WebhookError):
        verify_token({}, None)
    with pytest.raises(WebhookError):
        verify_token({"token": "wrong"}, None)


def test_handle_alert_records_human_gated_proposal(desk_env: Path) -> None:
    mem = DeskMemory()
    mem.learn("swing-equity-1d-trend", "AAPL", "D", 0.9)
    mem.save()
    rec = handle_alert(json.dumps(_alert()).encode())
    assert rec.status == "pending" and rec.ticker == "AAPL" and rec.price == 191.25
    assert rec.known_preset is True and rec.market == "equity"
    assert rec.memory_trust == pytest.approx(0.27, abs=1e-3)  # eta 0.3 × 0.9
    assert rec.motor["requires_human"] is True and rec.motor["action"] == "enter_long"
    items = load_alerts()
    assert len(items) == 1 and items[0]["id"] == rec.id
    # memory saw the alert as an episode and connectome state advanced
    again = DeskMemory.load()
    assert again.episodes[-1]["kind"] == "tradingview.alert" and again.connectome["steps"] == 1

    exit_rec = handle_alert(_alert(event="exit_long", preset="unknown-preset"))
    assert exit_rec.known_preset is False and exit_rec.motor["action"] in ("exit", "reduce", "hold")
    assert len(load_alerts()) == 2 and load_alerts(status="pending", limit=1)[0]["id"] == exit_rec.id


def test_respond_alert_records_decision_without_executing(desk_env: Path) -> None:
    rec = handle_alert(_alert())
    out = respond_alert(rec.id, "approve", note="looks fine")
    assert out["status"] == "approved" and out["executed"] is False and out["responded_at"]
    assert load_alerts(status="approved")[0]["note"] == "looks fine"
    assert load_alerts(status="pending") == []
    rej = respond_alert(rec.id, "REJECT")
    assert rej["status"] == "rejected"
    with pytest.raises(WebhookError):
        respond_alert(rec.id, "execute")
    with pytest.raises(WebhookError):
        respond_alert("missing", "ack")


def test_handle_alert_rejects_bad_token(desk_env: Path, monkeypatch) -> None:
    monkeypatch.setenv("AOA_TRADINGVIEW_WEBHOOK_SECRET", "s3cret")
    with pytest.raises(WebhookError):
        handle_alert(_alert())
    rec = handle_alert(_alert(), header_token="s3cret")
    assert rec.status == "pending"
    rec2 = handle_alert(_alert(token="s3cret"))
    assert rec2.id != rec.id
    assert not os.path.exists(desk_env / "data")  # nothing leaked outside the env paths


# --------------------------------------------------------------------------- #
# web routes
# --------------------------------------------------------------------------- #


def test_web_webhook_routes(desk_env: Path, fake_broker, fake_llm, monkeypatch, tmp_path) -> None:
    pytest.importorskip("fastapi")
    try:
        import httpx2  # noqa: F401
    except ImportError:  # pragma: no cover - fallback when httpx2 extra missing
        pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    from aoa.config import Config, RiskLimits
    from aoa.web.app import create_app

    cfg = Config(
        anthropic_api_key="x", alpaca_key_id="x", alpaca_secret_key="x", universe=("AAPL",), dry_run=True,
        news_enabled=False, web_auto_loop=False, analytics_enabled=False,
        journal_path=tmp_path / "j.jsonl", risk=RiskLimits(max_position_pct=0.10, max_orders_per_cycle=5),
    )
    monkeypatch.setattr("aoa.cli.build_broker", lambda c: fake_broker)
    monkeypatch.setattr("aoa.cli.build_llm", lambda c: fake_llm)
    monkeypatch.setattr("aoa.cli.build_news", lambda c: __import__("aoa.data.news", fromlist=["NullNewsFeed"]).NullNewsFeed())
    monkeypatch.setenv("AOA_TRADINGVIEW_WEBHOOK_SECRET", "hook")
    with TestClient(create_app(cfg)) as tc:
        r = tc.post("/api/tradingview/webhook", content=json.dumps(_alert()))
        assert r.status_code == 400 and "token" in r.json()["detail"]
        r = tc.post("/api/tradingview/webhook", content=json.dumps(_alert()), headers={"X-AOA-Token": "hook"})
        assert r.status_code == 200
        body = r.json()
        assert body["accepted"] and body["requires_human"] and body["alert"]["motor"]["requires_human"]
        alert_id = body["alert"]["id"]
        r = tc.get("/api/tradingview/alerts", params={"status": "pending"})
        assert [a["id"] for a in r.json()["items"]] == [alert_id]
        r = tc.post(f"/api/tradingview/alerts/{alert_id}/respond", json={"action": "approve", "note": "ok"})
        assert r.status_code == 200 and r.json()["executed"] is False
        r = tc.post(f"/api/tradingview/alerts/{alert_id}/respond", json={"action": "fire"})
        assert r.status_code == 400
        r = tc.post("/api/tradingview/webhook", content="garbage", headers={"X-AOA-Token": "hook"})
        assert r.status_code == 400
    # the broker fake saw no orders
    assert not getattr(fake_broker, "orders", [])
    assert (tmp_path / "j.jsonl").is_file() and "tradingview.alert" in (tmp_path / "j.jsonl").read_text()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_presets_and_pine(desk_env: Path, capsys) -> None:
    assert main(["tradingview", "presets"]) == 0
    out = capsys.readouterr().out
    assert "hft-crypto-1s-momentum" in out and f"{len(PRESETS)} presets" in out
    assert main(["tv", "presets", "--horizon", "hft", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows and all(r["horizon"] == "hft" for r in rows)
    assert main(["tv", "pine", "swing-equity-1d-trend", "--timeframe", "60"]) == 0
    src = capsys.readouterr().out
    assert src.startswith("//@version=6") and "timeframe=1 hour" in src
    assert main(["tv", "pine", "--all", "--dir", str(desk_env / "pine")]) == 0
    assert len(list((desk_env / "pine").glob("*.pine"))) == len(PRESETS)
    assert main(["tv", "pine"]) == 2


def test_cli_backtest_desk_memory_connectome(desk_env: Path, capsys) -> None:
    code = main(["tv", "backtest", "swing-equity-1d-trend", "--symbol", "AAPL", "--source", "synthetic", "--limit", "600", "--seed", "3", "--folds", "2", "--monte-carlo", "--trades", "--json"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["source"] == "synthetic" and out["n_bars"] == 600
    assert "walk_forward" in out and "monte_carlo" in out and "trades" in out
    assert main(["tv", "backtest", "swing-equity-1d-trend", "--symbol", "AAPL", "--source", "synthetic", "--limit", "400", "--seed", "3"]) == 0
    assert "never_live: True" in capsys.readouterr().out

    code = main(["tv", "desk", "run", "--symbols", "AAPL,ETH-USD", "--presets", "swing-equity-1d-trend,position-crypto-1d-trend", "--source", "synthetic", "--limit", "500", "--seed", "1", "--folds", "0", "--no-monte-carlo", "--no-fundamentals"])
    assert code == 0
    out = capsys.readouterr().out
    assert "TradingView desk run" in out and "human approval required" in out
    assert (desk_env / "data" / "tradingview" / "reports" / "latest.json").is_file()

    assert main(["tv", "desk", "status"]) == 0
    status = capsys.readouterr().out
    assert "lead: Julie" in status and "last run:" in status
    assert main(["tv", "memory"]) == 0
    assert "preset trust" in capsys.readouterr().out
    assert main(["tv", "memory", "--json"]) == 0
    ctx = json.loads(capsys.readouterr().out)
    assert ctx["synapses"] == 2
    assert main(["tv", "connectome", "status"]) == 0
    assert "mushroom_body" in capsys.readouterr().out
    assert main(["tv", "connectome", "step", "--trend", "0.9", "--momentum", "0.7", "--json"]) == 0
    cmd = json.loads(capsys.readouterr().out)
    assert cmd["action"] == "enter_long" and cmd["requires_human"] is True


def test_cli_universe_offline(desk_env: Path, capsys) -> None:
    assert main(["tv", "universe", "--offline", "--n", "12", "--csv", str(desk_env / "u.csv"), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["meta"]["source"] == "fallback" and len(out["entries"]) == 12
    assert (desk_env / "u.csv").read_text().splitlines()[0] == "symbol,name,exchange"
    assert main(["tv", "universe", "--offline", "--n", "5"]) == 0
    assert "US equity universe" in capsys.readouterr().out
