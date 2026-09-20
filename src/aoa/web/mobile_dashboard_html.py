"""Serve the built Ant Design Mobile shell from static assets."""

from __future__ import annotations

from pathlib import Path

MOBILE_STATIC_DIR = Path(__file__).resolve().parent / "static" / "mobile"
MOBILE_INDEX = MOBILE_STATIC_DIR / "index.html"
MOBILE_ASSETS_DIR = MOBILE_STATIC_DIR / "assets"


def mobile_index_html() -> str:
    """Return the built ``index.html`` text (raises FileNotFoundError if missing)."""
    return MOBILE_INDEX.read_text(encoding="utf-8")


def mobile_ui_ready() -> bool:
    return MOBILE_INDEX.is_file() and MOBILE_ASSETS_DIR.is_dir()
