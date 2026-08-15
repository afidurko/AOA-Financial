"""Package version — single source via installed distribution metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def package_version() -> str:
    try:
        return version("aoa-financial")
    except PackageNotFoundError:
        return "0.0.0-dev"
