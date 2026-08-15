"""Tests for the unified microstructure workspace catalog."""

from __future__ import annotations

from aoa.hftbacktest import HAS_HFTBACKTEST
from aoa.microstructure import catalog_status
from aoa.microstructure.catalog import _lane_available


def test_catalog_lists_core_lanes():
    status = catalog_status()
    assert status["offline_only"] is True
    assert status["never_live"] is True
    names = {row["lane"] for row in status["lanes"]}
    assert {
        "avellaneda",
        "visualhft",
        "hftbacktest",
        "orderbook",
        "hft_patterns",
        "hftish_patterns",
        "sgx_orderbook",
    } <= names
    # Pure-Python lanes always available; hftbacktest tracks optional install.
    by_name = {row["lane"]: row for row in status["lanes"]}
    assert by_name["avellaneda"]["available"] is True
    assert by_name["visualhft"]["available"] is True
    assert by_name["orderbook"]["available"] is True
    assert by_name["hft_patterns"]["available"] is True
    assert by_name["hftish_patterns"]["available"] is True
    assert by_name["sgx_orderbook"]["available"] is True
    assert by_name["hftbacktest"]["available"] is HAS_HFTBACKTEST
    if not HAS_HFTBACKTEST:
        assert "pip install" in str(by_name["hftbacktest"].get("hint", ""))
    assert status["available_count"] == sum(1 for row in status["lanes"] if row["available"])
    assert "Enum" not in by_name["hftish_patterns"]["symbols"]
    assert "calibrate_spread_bands" in by_name["hft_patterns"]["symbols"]


def test_lane_available_semantics():
    assert _lane_available({"available": False, "installed": True}) is False
    assert _lane_available({"installed": False}) is False
    assert _lane_available({"ok": True, "installed": True}) is True
    assert _lane_available({"installed": True}) is True
