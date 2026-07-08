"""Tests for one-step Moomoo activation helpers."""

from __future__ import annotations

import os

from aoa.activate import (
    DEFAULT_PROFILE,
    ensure_profile,
    ollama_has_model,
    opend_reachable,
    wait_for_opend,
)


def test_opend_reachable_true(monkeypatch):
    class FakeSock:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        "aoa.activate.socket.create_connection",
        lambda addr, timeout=2.0: FakeSock(),
    )
    assert opend_reachable("127.0.0.1", 11111) is True


def test_opend_reachable_false(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr("aoa.activate.socket.create_connection", boom)
    assert opend_reachable("127.0.0.1", 11111) is False


def test_wait_for_opend_succeeds(monkeypatch):
    calls = {"n": 0}

    def flip(*args, **kwargs):
        calls["n"] += 1
        return calls["n"] >= 2

    monkeypatch.setattr("aoa.activate.opend_reachable", flip)
    monkeypatch.setattr("aoa.activate.time.sleep", lambda _: None)
    assert wait_for_opend("127.0.0.1", 11111, timeout_sec=10, poll_sec=0) is True


def test_wait_for_opend_times_out(monkeypatch):
    monkeypatch.setattr("aoa.activate.opend_reachable", lambda *a, **k: False)
    monkeypatch.setattr("aoa.activate.time.sleep", lambda _: None)
    assert wait_for_opend("127.0.0.1", 11111, timeout_sec=0.01, poll_sec=0) is False


def test_ensure_profile_defaults_to_paper_dry(monkeypatch, tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "paper-dry.env").write_text("AOA_ENV=paper-dry\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AOA_PROFILE", raising=False)
    monkeypatch.setenv("AOA_ENV", "paper-dry")
    ensure_profile()
    assert os.environ.get("AOA_PROFILE") == DEFAULT_PROFILE


def test_ensure_profile_sets_paper_dry_when_only_aoa_env(monkeypatch, tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "paper-dry.env").write_text(
        "AOA_LLM_PROVIDER=ollama\nAOA_ENV=paper-dry\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AOA_PROFILE", raising=False)
    monkeypatch.setenv("AOA_ENV", "paper-dry")
    ensure_profile()
    assert os.environ.get("AOA_PROFILE") == "paper-dry"
    assert os.environ.get("AOA_LLM_PROVIDER") == "ollama"


def test_cmd_activate_no_wait_fails_without_opend(monkeypatch):
    from aoa.activate import auto_activate
    from aoa.config import Config

    monkeypatch.setattr("aoa.activate.opend_reachable", lambda *a, **k: False)
    cfg = Config(env="paper-dry", broker="moomoo", llm_provider="ollama")
    assert auto_activate(cfg, skip_opend_wait=True, verbose=False) == 1


def test_cmd_activate_skip_wait_ok(monkeypatch):
    from aoa.activate import auto_activate
    from aoa.config import Config

    monkeypatch.setattr("aoa.activate.opend_reachable", lambda *a, **k: True)
    monkeypatch.setattr("aoa.activate.ollama_reachable", lambda: True)
    monkeypatch.setattr("aoa.activate._openai_sdk_available", lambda: True)
    monkeypatch.setattr("aoa.activate.ollama_has_model", lambda model: True)
    monkeypatch.setattr("aoa.activate._verify_moomoo_ready", lambda cfg: None)
    cfg = Config(env="paper-dry", broker="moomoo", llm_provider="ollama", auto_activate=True)
    assert auto_activate(cfg, skip_opend_wait=True, verbose=False) == 0


def test_auto_activate_strict_fails_missing_ollama_model(monkeypatch):
    from aoa.activate import auto_activate
    from aoa.config import Config

    monkeypatch.setattr("aoa.activate.opend_reachable", lambda *a, **k: True)
    monkeypatch.setattr("aoa.activate.ollama_reachable", lambda: True)
    monkeypatch.setattr("aoa.activate._openai_sdk_available", lambda: True)
    monkeypatch.setattr("aoa.activate.ollama_has_model", lambda model: False)
    monkeypatch.setattr("aoa.activate._verify_moomoo_ready", lambda cfg: None)
    cfg = Config(
        env="paper-dry",
        broker="moomoo",
        llm_provider="ollama",
        model="llama3.1",
        auto_activate=True,
        auto_activate_strict=True,
    )
    assert auto_activate(cfg, skip_opend_wait=True, verbose=False) == 1


def test_auto_activate_disabled_skips(monkeypatch):
    from aoa.activate import auto_activate
    from aoa.config import Config

    monkeypatch.setattr("aoa.activate.opend_reachable", lambda *a, **k: False)
    cfg = Config(env="paper-dry", broker="moomoo", auto_activate=False)
    assert auto_activate(cfg) == 0


def test_ollama_has_model_matches_tag(monkeypatch):
    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"models":[{"name":"llama3.1:latest"}]}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResp())
    assert ollama_has_model("llama3.1") is True
