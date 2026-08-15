"""Tests for the unified microstructure workspace catalog."""

from __future__ import annotations

from aoa.microstructure import catalog_status


def test_catalog_lists_core_lanes():
    status = catalog_status()
    assert status["offline_only"] is True
    assert status["never_live"] is True
    assert status["available_count"] >= 4
    names = {row["lane"] for row in status["lanes"]}
    assert {"avellaneda", "visualhft", "hftbacktest", "orderbook", "hft_patterns"} <= names
    # Pattern companions may be missing until their branches land; still listed.
    assert "hftish_patterns" in names
    assert "sgx_orderbook" in names
