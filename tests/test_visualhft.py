"""Tests for the VisualHFT microstructure research lane."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from aoa.cli import cmd_visualhft_smoke, cmd_visualhft_status, cmd_visualhft_studies
from aoa.visualhft import probe_status, run_synthetic_smoke
from aoa.visualhft.studies import TradePrint, VPINState, lob_imbalance, order_to_trade_ratio


def test_probe_status_shape():
    status = probe_status()
    assert status["available"] is True
    assert status["offline_only"] is True
    assert status["never_live"] is True
    assert "lob_imbalance" in status["studies_ported"]
    assert "vpin" in status["studies_ported"]
    assert "market_resilience" not in status["studies_ported"]
    assert status["ported_count"] == 3
    assert status["fork"].endswith("/VisualHFT")


def test_lob_imbalance_formula():
    # Equal size → 0
    assert lob_imbalance([10, 10], [10, 10]) == 0.0
    # Empty side → 0 (VisualHFT requires both sides present)
    assert lob_imbalance([5, 5], []) == 0.0
    assert lob_imbalance([], [5, 5]) == 0.0
    # Zero-size asks still count as present levels → +1
    assert lob_imbalance([5, 5], [0, 0]) == 1.0
    assert lob_imbalance([8, 2], [2, 0], book_depth=2) == (10 - 2) / (10 + 2)
    # Depth truncation
    assert lob_imbalance([10, 100], [10, 0], book_depth=1) == 0.0


def test_order_to_trade_ratio_formula():
    # (10 + 5 + 2*3) / 5 - 1 = 21/5 - 1 = 3.2
    assert order_to_trade_ratio(
        added_delta=10, deleted_delta=5, updated_delta=3, trade_count=5
    ) == 3.2
    # Floor of 1 when no trades
    assert order_to_trade_ratio(
        added_delta=4, deleted_delta=0, updated_delta=0, trade_count=0
    ) == 3.0


def test_order_to_trade_ratio_rejects_negatives():
    with pytest.raises(ValueError, match=">= 0"):
        order_to_trade_ratio(
            added_delta=-1, deleted_delta=0, updated_delta=0, trade_count=1
        )
    with pytest.raises(ValueError, match="floor"):
        order_to_trade_ratio(
            added_delta=1, deleted_delta=0, updated_delta=0, trade_count=1, floor=0
        )


def test_vpin_completes_buckets():
    state = VPINState(bucket_volume=10.0, n_buckets=3, mid_price=100.0)
    # Ten units of buys fill one bucket → imbalance 1.0
    assert state.on_trade(TradePrint(price=100.5, size=10.0)) == 1.0
    assert state.completed_buckets == 1
    # Balanced next bucket: 5 buy + 5 sell
    state.on_trade(TradePrint(price=100.5, size=5.0))
    v = state.on_trade(TradePrint(price=99.5, size=5.0))
    assert abs(v - 0.5) < 1e-9  # mean of 1.0 and 0.0


def test_vpin_large_trade_spans_buckets():
    state = VPINState(bucket_volume=10.0, n_buckets=5, mid_price=100.0)
    state.on_trade(TradePrint(price=101.0, size=35.0))
    assert state.completed_buckets == 3
    assert abs(state.current_volume - 5.0) < 1e-9


def test_synthetic_smoke_ok():
    result = run_synthetic_smoke(n_trades=120, seed=7)
    assert result.ok
    assert result.vpin_buckets >= 1
    assert -1.0 <= result.lob_imbalance <= 1.0
    assert result.lob_imbalance > 0
    assert 0.0 <= result.vpin <= 1.0
    assert result.mid_price == round(result.mid_price, 2)
    payload = result.to_dict()
    assert payload["ok"] is True
    assert payload["n_trades"] == 120
    assert "vpin_buckets" in payload


def test_synthetic_smoke_rejects_tiny_tape():
    with pytest.raises(ValueError, match="n_trades"):
        run_synthetic_smoke(n_trades=5, seed=1)


def test_cli_visualhft_status_help():
    proc = subprocess.run(
        [sys.executable, "-m", "aoa.cli", "visualhft", "status", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--json" in proc.stdout


def test_cmd_visualhft_status_json(capsys):
    code = cmd_visualhft_status(as_json=True)
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["offline_only"] is True
    assert out["available"] is True


def test_cmd_visualhft_smoke_json(capsys):
    code = cmd_visualhft_smoke(n_trades=80, seed=3, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["ok"] is True
    assert data["vpin_buckets"] >= 1


def test_cmd_visualhft_smoke_rejects_tiny_tape(capsys):
    code = cmd_visualhft_smoke(n_trades=3, seed=1, as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["ok"] is False
    assert "n_trades" in data["error"]


def test_cli_visualhft_skips_env_template(tmp_path, monkeypatch, capsys):
    """Offline visualhft commands must not create .env as a side effect."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("AOA_ENV=paper\n", encoding="utf-8")
    from aoa.cli import main

    code = main(["visualhft", "status", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["offline_only"] is True
    assert not (tmp_path / ".env").exists()


def test_cmd_visualhft_studies_json(capsys):
    code = cmd_visualhft_studies(as_json=True, ported_only=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    ids = {row["id"] for row in data["studies"]}
    assert ids == {"lob_imbalance", "vpin", "order_to_trade_ratio"}
    assert all(row["ported"] for row in data["studies"])
