"""Catalog of VisualHFT studies available in the Python research lane."""

from __future__ import annotations

from typing import Any

STUDY_CATALOG: dict[str, dict[str, Any]] = {
    "lob_imbalance": {
        "id": "lob_imbalance",
        "title": "LOB Imbalance",
        "source_plugin": "Studies.LOBImbalance",
        "range": "[-1, 1]",
        "summary": (
            "(bid_size - ask_size) / (bid_size + ask_size) over top-N book levels "
            "(VisualHFT OrderFlowAnalysis.Calculate_OrderImbalance)."
        ),
        "ported": True,
    },
    "vpin": {
        "id": "vpin",
        "title": "VPIN",
        "source_plugin": "Studies.VPIN",
        "range": "[0, 1]",
        "summary": (
            "Volume-synchronized probability of informed trading: rolling mean of "
            "|V_buy - V_sell| / V_bucket (Easley, López de Prado & O'Hara)."
        ),
        "ported": True,
    },
    "order_to_trade_ratio": {
        "id": "order_to_trade_ratio",
        "title": "Order-to-Trade Ratio",
        "source_plugin": "Studies.OTT_Ratio",
        "range": "unbounded (≥ -1 typical)",
        "summary": (
            "L2 OTR = (addedΔ + deletedΔ + 2×updatedΔ) / max(trades, 1) - 1 "
            "(VisualHFT OrderToTradeRatioStudy)."
        ),
        "ported": True,
    },
    "market_resilience": {
        "id": "market_resilience",
        "title": "Market Resilience",
        "source_plugin": "Studies.MarketResilience",
        "range": "desktop study",
        "summary": (
            "Recovery dynamics after liquidity shocks — remains desktop-only for now; "
            "use VisualHFT WPF host or extend this package later."
        ),
        "ported": False,
    },
}


def list_studies(*, ported_only: bool = False) -> list[dict[str, Any]]:
    """Return study descriptors sorted by id."""
    rows = list(STUDY_CATALOG.values())
    if ported_only:
        rows = [r for r in rows if r.get("ported")]
    return sorted(rows, key=lambda r: r["id"])
