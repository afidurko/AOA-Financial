"""Status probe for the VisualHFT research lane (no Windows runtime required)."""

from __future__ import annotations

from typing import Any

from aoa.visualhft.catalog import STUDY_CATALOG

FORK_URL = "https://github.com/afidurko/VisualHFT"
UPSTREAM_URL = "https://github.com/visualHFT/VisualHFT"
HOMEPAGE = "https://visualHFT.com"


def probe_status() -> dict[str, Any]:
    """Return a JSON-serializable status dict for ``aoa visualhft status``."""
    ported = sorted(k for k, v in STUDY_CATALOG.items() if v.get("ported"))
    return {
        "available": True,
        "runtime": "python-research",
        "desktop_host": "windows-dotnet10-wpf",
        "studies_ported": ported,
        "study_count": len(STUDY_CATALOG),
        "ported_count": len(ported),
        "fork": FORK_URL,
        "upstream": UPSTREAM_URL,
        "homepage": HOMEPAGE,
        "offline_only": True,
        "never_live": True,
        "hint": "aoa visualhft smoke",
        "desktop_hint": (
            "Clone fork + oxyplot on Windows, open VisualHFT.sln, F5 — "
            "see docs/how-to/visualhft-integration.md"
        ),
    }
