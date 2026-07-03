"""Tests for the LLM client fallbacks and validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aoa.llm.client import LLMClient, LLMError


def _text_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def test_invalid_effort_rejected():
    with pytest.raises(LLMError, match="Invalid effort"):
        LLMClient("sk-test", effort="turbo")


def test_structured_falls_back_when_advanced_call_fails():
    client = LLMClient("sk-test")
    with patch.object(
        client._client.messages,
        "create",
        side_effect=[
            RuntimeError("unsupported thinking param"),
            _text_response('{"ok": true}'),
        ],
    ) as mock_create:
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        }
        result = client.structured("sys", "prompt", schema, max_tokens=100)
    assert result == {"ok": True}
    assert mock_create.call_count == 2


def test_ping_requires_ok_true():
    client = LLMClient("sk-test")
    with patch.object(
        client,
        "structured",
        return_value={"ok": False},
    ):
        with pytest.raises(LLMError, match="Unexpected LLM ping"):
            client.ping()
