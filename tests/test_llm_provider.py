"""Tests for multi-provider LLM support (anthropic | openai | ollama)."""

from __future__ import annotations

import types

import pytest

from aoa.config import Config
from aoa.llm import client as client_module
from aoa.llm.client import LLMClient, LLMError


class _FakeCompletions:
    calls: list[dict] = []

    def create(self, **kwargs):
        _FakeCompletions.calls.append(kwargs)
        choice = types.SimpleNamespace(message=types.SimpleNamespace(content=FakeOpenAI.content))
        return types.SimpleNamespace(choices=[choice])


class FakeOpenAI:
    """Stand-in for the OpenAI SDK client so tests need no network or package."""

    last_init: dict | None = None
    content = '{"ok": true}'

    def __init__(self, **kwargs):
        FakeOpenAI.last_init = kwargs
        self.chat = types.SimpleNamespace(completions=_FakeCompletions())


@pytest.fixture
def fake_openai(monkeypatch):
    FakeOpenAI.last_init = None
    FakeOpenAI.content = '{"ok": true}'
    monkeypatch.setattr(client_module, "OpenAI", FakeOpenAI)
    return FakeOpenAI


# ---------------------------------------------------------------- config
def test_llm_api_key_selects_provider_key():
    assert Config(llm_provider="anthropic", anthropic_api_key="a").llm_api_key == "a"
    assert Config(llm_provider="openai", openai_api_key="o").llm_api_key == "o"
    assert Config(llm_provider="ollama").llm_api_key == "ollama"


def test_validate_openai_requires_key():
    problems = Config(env="paper-dry", broker="moomoo", llm_provider="openai").validate()
    assert any("OPENAI_API_KEY" in p for p in problems)
    assert not any("ANTHROPIC_API_KEY" in p for p in problems)


def test_validate_ollama_needs_no_key():
    problems = Config(env="paper-dry", broker="moomoo", llm_provider="ollama").validate()
    assert not any("API_KEY" in p for p in problems)


def test_validate_unknown_provider():
    problems = Config(env="paper-dry", broker="moomoo", llm_provider="bogus").validate()
    assert any("AOA_LLM_PROVIDER" in p for p in problems)


def test_from_env_parses_provider(monkeypatch):
    monkeypatch.setenv("AOA_LLM_PROVIDER", "OpenAI")
    monkeypatch.setenv("AOA_LLM_BASE_URL", "https://gw.example/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    cfg = Config.from_env(load_dotenv=False)
    assert cfg.llm_provider == "openai"
    assert cfg.llm_base_url == "https://gw.example/v1"
    assert cfg.openai_api_key == "sk-x"


# ---------------------------------------------------------------- client
def test_invalid_provider_raises():
    with pytest.raises(LLMError):
        LLMClient("k", provider="bogus")


def test_ollama_defaults_base_url_and_key(fake_openai):
    LLMClient("", provider="ollama")
    assert fake_openai.last_init["base_url"] == "http://localhost:11434/v1"
    assert fake_openai.last_init["api_key"] == "ollama"


def test_openai_requires_key(fake_openai):
    with pytest.raises(LLMError):
        LLMClient("", provider="openai")


def test_openai_complete_and_structured(fake_openai):
    fake_openai.content = "hello world"
    llm = LLMClient("sk", provider="openai", base_url="https://gw/v1")
    assert fake_openai.last_init["base_url"] == "https://gw/v1"
    assert llm.complete("sys", "hi") == "hello world"

    fake_openai.content = '{"ok": true}'
    assert llm.structured("sys", "hi", {"type": "object"}) == {"ok": True}


def test_openai_structured_extracts_embedded_json(fake_openai):
    fake_openai.content = 'here you go: {"ok": true} done'
    llm = LLMClient("sk", provider="openai")
    assert llm.structured("sys", "hi", {"type": "object"}) == {"ok": True}


def test_ping_ok(fake_openai):
    fake_openai.content = '{"ok": true}'
    LLMClient("sk", provider="openai").ping()
