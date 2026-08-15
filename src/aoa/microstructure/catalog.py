"""Unified catalog of offline microstructure / HFT research lanes.

Meshes companion workspaces (Avellaneda–Stoikov, VisualHFT, hftbacktest,
orderbook, strategy-pattern ports) into one status surface. Never live.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _lane_available(status: dict[str, Any]) -> bool:
    """Derive availability from probe semantics (installed / ok / available)."""
    if "available" in status:
        return bool(status["available"])
    if "ok" in status:
        return bool(status["ok"])
    if "installed" in status:
        return bool(status["installed"])
    return True


def _safe_probe(label: str, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        status = dict(loader())
        status["lane"] = label
        status["available"] = _lane_available(status)
        return status
    except Exception as exc:  # noqa: BLE001 — catalog must stay resilient
        return {
            "lane": label,
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "offline_only": True,
            "never_live": True,
        }


def _module_symbols(mod: Any) -> list[str]:
    names = getattr(mod, "__all__", None)
    if names:
        return sorted(str(n) for n in names if hasattr(mod, n))
    return sorted(
        n
        for n, obj in vars(mod).items()
        if not n.startswith("_") and callable(obj) and getattr(obj, "__module__", "") == mod.__name__
    )


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


def _probe_pattern_module(
    *,
    module: str,
    companion: str,
    cli_hint: str,
) -> dict[str, Any]:
    import importlib

    mod = importlib.import_module(module)
    return {
        "available": True,
        "runtime": "python-research",
        "module": module,
        "companion": companion,
        "cli_hint": cli_hint,
        "offline_only": True,
        "never_live": True,
        "symbols": _module_symbols(mod),
    }


def _probe_hft_patterns() -> dict[str, Any]:
    return _probe_pattern_module(
        module="aoa.research.hft_patterns",
        companion="https://github.com/afidurko/hft",
        cli_hint="import aoa.research.hft_patterns",
    )


def _probe_hftish() -> dict[str, Any]:
    return _probe_pattern_module(
        module="aoa.research.hftish_patterns",
        companion="https://github.com/afidurko/example-hftish",
        cli_hint="import aoa.research.hftish_patterns",
    )


def _probe_sgx() -> dict[str, Any]:
    return _probe_pattern_module(
        module="aoa.research.sgx_orderbook_patterns",
        companion="https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy",
        cli_hint="import aoa.research.sgx_orderbook_patterns",
    )


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
    for name, loader, fallback_hint in LANES:
        row = _safe_probe(name, loader)
        row.setdefault("hint", fallback_hint)
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
