"""Unified catalog of offline microstructure / HFT research lanes.

Meshes companion workspaces (Avellaneda–Stoikov, VisualHFT, hftbacktest,
orderbook, strategy-pattern ports) into one status surface. Never live.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _safe_probe(label: str, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        status = loader()
        status.setdefault("lane", label)
        status.setdefault("available", True)
        return status
    except Exception as exc:  # noqa: BLE001 — catalog must stay resilient
        return {
            "lane": label,
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "offline_only": True,
            "never_live": True,
        }


def _probe_avellaneda() -> dict[str, Any]:
    from aoa.avellaneda_stoikov import probe_status

    return probe_status()


def _probe_visualhft() -> dict[str, Any]:
    from aoa.visualhft import probe_status

    return probe_status()


def _probe_hftbacktest() -> dict[str, Any]:
    from aoa.hftbacktest import probe_status

    return probe_status()


def _probe_orderbook() -> dict[str, Any]:
    from aoa.orderbook import probe_status

    return probe_status()


def _probe_hft_patterns() -> dict[str, Any]:
    import aoa.research.hft_patterns as mod

    return {
        "available": True,
        "runtime": "python-research",
        "module": "aoa.research.hft_patterns",
        "companion": "https://github.com/afidurko/hft",
        "cli_hint": "import aoa.research.hft_patterns",
        "offline_only": True,
        "never_live": True,
        "symbols": sorted(
            n
            for n in (
                "calibrate_spread_bands",
                "open_side_from_bands",
                "ma_cross_signal",
                "mid_maker_side",
            )
            if hasattr(mod, n)
        ),
    }


def _probe_hftish() -> dict[str, Any]:
    import aoa.research.hftish_patterns as mod

    return {
        "available": True,
        "runtime": "python-research",
        "module": "aoa.research.hftish_patterns",
        "companion": "https://github.com/afidurko/example-hftish",
        "cli_hint": "import aoa.research.hftish_patterns",
        "offline_only": True,
        "never_live": True,
        "symbols": sorted(n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n))),
    }


def _probe_sgx() -> dict[str, Any]:
    import aoa.research.sgx_orderbook_patterns as mod

    return {
        "available": True,
        "runtime": "python-research",
        "module": "aoa.research.sgx_orderbook_patterns",
        "companion": "https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy",
        "cli_hint": "import aoa.research.sgx_orderbook_patterns",
        "offline_only": True,
        "never_live": True,
        "symbols": sorted(n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n))),
    }


LANES: tuple[tuple[str, Callable[[], dict[str, Any]], str], ...] = (
    ("avellaneda", _probe_avellaneda, "aoa avellaneda status"),
    ("visualhft", _probe_visualhft, "aoa visualhft status"),
    ("hftbacktest", _probe_hftbacktest, "aoa hft status"),
    ("orderbook", _probe_orderbook, "aoa hft book-smoke"),
    ("hft_patterns", _probe_hft_patterns, "docs/how-to/hft-reference.md"),
    ("hftish_patterns", _probe_hftish, "docs/how-to/example-hftish-reference.md"),
    ("sgx_orderbook", _probe_sgx, "docs/how-to/sgx-orderbook-reference.md"),
)


def catalog_status() -> dict[str, Any]:
    """Aggregate status for every microstructure research lane in this workspace."""
    lanes: list[dict[str, Any]] = []
    for name, loader, hint in LANES:
        row = _safe_probe(name, loader)
        row["hint"] = hint
        lanes.append(row)
    available = sum(1 for row in lanes if row.get("available"))
    return {
        "available": available > 0,
        "lane_count": len(lanes),
        "available_count": available,
        "offline_only": True,
        "never_live": True,
        "lanes": lanes,
        "docs": "docs/how-to/microstructure-lanes.md",
        "hint": "aoa microstructure status --json",
    }
