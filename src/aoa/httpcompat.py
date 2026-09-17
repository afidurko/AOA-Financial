"""HTTP client compatibility — prefer httpx, fall back to httpx2."""

from __future__ import annotations

try:
    import httpx
except ImportError:  # pragma: no cover - web extra may only ship httpx2
    import httpx2 as httpx

__all__ = ["httpx"]
