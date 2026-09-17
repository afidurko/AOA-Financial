"""Tests for HTTP client compatibility shim."""

from __future__ import annotations


def test_httpcompat_exports_client():
    from aoa.httpcompat import httpx

    assert hasattr(httpx, "Client")
    assert hasattr(httpx, "post")
    assert hasattr(httpx, "get")
