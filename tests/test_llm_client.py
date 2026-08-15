"""Tests for the LLM client fallbacks and validation."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from aoa.cli import build_llm
from aoa.config import Config
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
        LLMClient("sk-test", provider="anthropic", effort="turbo")


def test_invalid_provider_rejected():
    with pytest.raises(LLMError, match="Invalid LLM provider"):
        LLMClient("sk-test", provider="ollama")


def test_default_provider_is_openai_compatible():
    client = LLMClient()
    assert client.provider == "openai_compatible"
    assert client.base_url == "http://127.0.0.1:8000/v1"
    assert client.model == "kimi-linear"


def test_openai_compatible_requires_base_url():
    with pytest.raises(LLMError, match="AOA_LLM_BASE_URL"):
        LLMClient(provider="openai_compatible", model="k3", base_url="")


def test_openai_compatible_defaults_base_url_when_omitted():
    client = LLMClient(provider="openai_compatible", model="k3")
    assert client.base_url == "http://127.0.0.1:8000/v1"


def test_structured_falls_back_when_advanced_call_fails():
    client = LLMClient("sk-test", provider="anthropic")
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
    client = LLMClient("sk-test", provider="anthropic")
    with patch.object(
        client,
        "structured",
        return_value={"ok": False},
    ):
        with pytest.raises(LLMError, match="Unexpected LLM ping"):
            client.ping()


def test_openai_compatible_structured_uses_chat_completions():
    client = LLMClient(
        "local",
        provider="openai_compatible",
        model="k3",
        base_url="http://127.0.0.1:8000/v1",
    )
    payload = {
        "choices": [
            {"message": {"content": json.dumps({"ok": True})}},
        ]
    }
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(payload).encode("utf-8")
    fake_resp.__enter__.return_value = fake_resp
    fake_resp.__exit__.return_value = None

    with patch("aoa.llm.client.urllib.request.urlopen", return_value=fake_resp) as mock_open:
        result = client.structured(
            "sys",
            "prompt",
            {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            },
            max_tokens=64,
        )

    assert result == {"ok": True}
    req = mock_open.call_args.args[0]
    assert req.full_url == "http://127.0.0.1:8000/v1/chat/completions"
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "k3"
    assert body["response_format"]["type"] == "json_schema"
    assert body["thinking_effort"] == "high"


def test_openai_compatible_http_error_surfaces_detail():
    client = LLMClient(
        provider="openai_compatible",
        model="k3",
        base_url="http://127.0.0.1:8000/v1",
    )
    err = HTTPError(
        "http://127.0.0.1:8000/v1/chat/completions",
        503,
        "unavailable",
        hdrs=None,
        fp=BytesIO(b'{"error":"busy"}'),
    )
    with patch("aoa.llm.client.urllib.request.urlopen", side_effect=err):
        with pytest.raises(LLMError, match="503"):
            client.complete("sys", "prompt", max_tokens=16)


def test_build_llm_defaults_to_openai_compatible():
    cfg = Config()
    client = build_llm(cfg)
    assert client.provider == "openai_compatible"
    assert client.base_url == "http://127.0.0.1:8000/v1"
    assert client.model == "kimi-linear"


def test_build_llm_openai_compatible():
    cfg = Config(
        llm_provider="openai_compatible",
        llm_base_url="http://127.0.0.1:8000/v1",
        llm_api_key="tok",
        model="kimi-linear",
        effort="medium",
    )
    client = build_llm(cfg)
    assert client.provider == "openai_compatible"
    assert client.base_url == "http://127.0.0.1:8000/v1"
    assert client.model == "kimi-linear"
    assert client.effort == "medium"


def test_build_llm_anthropic_opt_in():
    cfg = Config(
        llm_provider="anthropic",
        anthropic_api_key="sk-test",
        model="claude-sonnet-4-6",
    )
    client = build_llm(cfg)
    assert client.provider == "anthropic"
    assert client.model == "claude-sonnet-4-6"
