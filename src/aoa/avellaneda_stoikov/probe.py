"""Status probe for the Avellaneda–Stoikov research lane."""

from __future__ import annotations

from typing import Any

FORK_URL = "https://github.com/afidurko/avellaneda-stoikov"
PAPER_NOTE = (
    "Avellaneda & Stoikov, High-frequency trading in a limit order book "
    "(Quantitative Finance, 2008)"
)


def probe_status() -> dict[str, Any]:
    """Return a JSON-serializable status dict for ``aoa avellaneda status``."""
    return {
        "available": True,
        "runtime": "python-research",
        "model": "avellaneda-stoikov",
        "modes": ["limited_horizon", "unlimited_horizon"],
        "fork": FORK_URL,
        "paper": PAPER_NOTE,
        "offline_only": True,
        "never_live": True,
        "hint": "aoa avellaneda smoke",
        "docs": "docs/how-to/avellaneda-stoikov.md",
    }
