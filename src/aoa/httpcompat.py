"""HTTP client compatibility — prefer httpx2 (web), fall back to httpx."""

from __future__ import annotations

try:
    import httpx2 as httpx
except ImportError:  # pragma: no cover - core install without [web]
    import httpx

__all__ = ["httpx"]
