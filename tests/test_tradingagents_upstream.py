"""Tests for optional upstream TradingAgents package integration."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tradingagents_propagate.py"
INDICATORS_SCRIPT = ROOT / "scripts" / "test_yfinance_indicators.py"


def _upstream_installed() -> bool:
    return importlib.util.find_spec("tradingagents") is not None


@pytest.mark.skipif(not _upstream_installed(), reason="tradingagents extra not installed")
def test_upstream_tradingagents_importable():
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    assert isinstance(DEFAULT_CONFIG, dict)
    assert TradingAgentsGraph is not None
    assert "llm_provider" in DEFAULT_CONFIG


def test_propagate_script_help():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "trade_date" in proc.stdout


def test_yfinance_indicators_script_help():
    proc = subprocess.run(
        [sys.executable, str(INDICATORS_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "lookback" in proc.stdout
    assert "indicator" in proc.stdout


def test_integration_doc_exists():
    """Regression: upg-007 integration audit doc stays in repo."""
    doc = ROOT / "docs" / "tradingagents" / "INTEGRATION.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    for heading in (
        "## Built-in swarm",
        "## Optional upstream package",
        "TradingAgentsGraph.propagate",
    ):
        assert heading in text
