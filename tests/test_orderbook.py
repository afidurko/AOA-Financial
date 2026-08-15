"""Tests for the vendored HFT-Orderbook integration."""

from __future__ import annotations

import json
import subprocess
import sys

from aoa.cli import cmd_hft_book_smoke, cmd_hft_status
from aoa.orderbook import HAS_ORDERBOOK, LimitOrderBook, Order, probe_status, run_book_smoke


def test_has_orderbook():
    assert HAS_ORDERBOOK is True


def test_probe_status_ok():
    status = probe_status()
    assert status["installed"] is True
    assert status["ok"] is True
    assert status["offline_only"] is True
    assert "afidurko/HFT-Orderbook" in status["upstream"]


def test_run_book_smoke():
    result = run_book_smoke()
    assert result.ok
    assert result.best_bid == 99.0
    assert result.best_ask == 101.0
    assert result.order_count == 2


def test_limit_order_book_queue():
    book = LimitOrderBook()
    book.process(Order(uid=1, is_bid=True, size=5, price=100))
    book.process(Order(uid=2, is_bid=True, size=10, price=100))
    assert len(book.best_bid) == 2
    assert book.best_bid.volume == 1500
    book.process(Order(uid=1, is_bid=True, size=0, price=100))
    assert len(book.best_bid) == 1
    assert book.best_bid.orders.head.uid == 2


def test_cmd_hft_book_smoke_json(capsys):
    code = cmd_hft_book_smoke(as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["ok"] is True


def test_cmd_hft_status_includes_orderbook(capsys):
    code = cmd_hft_status(as_json=True)
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["orderbook"]["ok"] is True
    assert "hftbacktest" in data


def test_cli_book_smoke_help():
    proc = subprocess.run(
        [sys.executable, "-m", "aoa.cli", "hft", "book-smoke", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--json" in proc.stdout
