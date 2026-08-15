"""Install / version probe for the optional hftbacktest extra."""

from __future__ import annotations

from typing import Any


def probe_status() -> dict[str, Any]:
    """Return a JSON-serializable status dict for ``aoa hft status``."""
    try:
        import hftbacktest as hbt
    except ImportError:
        return {
            "installed": False,
            "version": None,
            "engine": None,
            "hint": 'pip install -e ".[hftbacktest]"',
            "upstream": "https://github.com/afidurko/hftbacktest",
            "offline_only": True,
        }

    version = getattr(hbt, "__version__", None)
    if version is None:
        try:
            from importlib.metadata import version as pkg_version

            version = pkg_version("hftbacktest")
        except Exception:  # pragma: no cover - metadata edge
            version = "unknown"

    return {
        "installed": True,
        "version": version,
        "engine": "HashMapMarketDepthBacktest",
        "hint": "aoa hft smoke",
        "upstream": "https://github.com/afidurko/hftbacktest",
        "offline_only": True,
    }
