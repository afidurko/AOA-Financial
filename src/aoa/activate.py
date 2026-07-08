"""One-step activation: wait for Moomoo OpenD, ensure local LLM, run doctor."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from shutil import which
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aoa.config import Config

DEFAULT_PROFILE = "paper-dry"
_OLLAMA_VERSION_URL = "http://127.0.0.1:11434/api/version"
_OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"


def opend_reachable(host: str, port: int, *, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_opend(
    host: str,
    port: int,
    *,
    timeout_sec: float = 300.0,
    poll_sec: float = 2.0,
    on_wait=None,
) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if opend_reachable(host, port):
            return True
        if on_wait:
            on_wait()
        time.sleep(poll_sec)
    return False


def ollama_reachable(url: str = _OLLAMA_VERSION_URL, *, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def start_ollama_serve() -> bool:
    """Start ``ollama serve`` in the background if the binary exists."""
    if not which("ollama"):
        return False
    if ollama_reachable():
        return True
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    for _ in range(15):
        time.sleep(1.0)
        if ollama_reachable():
            return True
    return False


def ollama_has_model(model: str, *, tags_url: str = _OLLAMA_TAGS_URL) -> bool:
    """Return True when ``model`` (e.g. llama3.1) appears in Ollama's tag list."""
    try:
        with urllib.request.urlopen(tags_url, timeout=3.0) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
        return False
    want = model.split(":")[0].lower()
    for entry in data.get("models", []):
        name = str(entry.get("name", "")).split(":")[0].lower()
        if name == want or want in name:
            return True
    return False


def _openai_sdk_available() -> bool:
    try:
        import openai  # noqa: F401

        return True
    except ImportError:
        return False


def _verify_moomoo_ready(cfg: Config) -> str | None:
    """Return an error message if OpenD is up but the broker API is not ready."""
    try:
        from aoa.health import verify_broker_ready

        verify_broker_ready(cfg)
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    return None


def ensure_profile() -> None:
    """Default to paper-dry (Moomoo + Ollama) when no profile is selected."""
    import os

    from aoa.config import load_env_files

    if not os.environ.get("AOA_PROFILE"):
        os.environ.setdefault("AOA_PROFILE", DEFAULT_PROFILE)
    load_env_files()


def print_activation_banner() -> None:
    print(
        "AOA activate — log into Moomoo OpenD on this machine, "
        "then all systems come online.\n"
        f"Profile: {DEFAULT_PROFILE} (Moomoo + local Ollama, paper dry-run)\n"
    )


def wait_message(host: str, port: int) -> None:
    print(
        f"  Waiting for Moomoo OpenD at {host}:{port} … "
        "(install from moomoo.com/download/OpenAPI, then log in)",
        file=sys.stderr,
        flush=True,
    )


def auto_activate(
    cfg: Config,
    *,
    wait_sec: float | None = None,
    skip_opend_wait: bool = False,
    run_doctor: bool = False,
    verbose: bool = False,
) -> int:
    """Wait for OpenD, ensure Ollama, optionally run doctor. Returns 0 on success."""
    if not cfg.auto_activate or cfg.is_test:
        return 0

    strict = cfg.auto_activate_strict
    timeout = wait_sec if wait_sec is not None else cfg.auto_activate_wait_sec

    if verbose:
        print_activation_banner()
    elif cfg.broker == "moomoo":
        print("Auto-activating (waiting for Moomoo OpenD)…", flush=True)

    if cfg.broker == "moomoo":
        host, port = cfg.moomoo_opend_host, cfg.moomoo_opend_port
        if skip_opend_wait:
            if not opend_reachable(host, port):
                print(f"OpenD not reachable at {host}:{port}.", file=sys.stderr)
                return 1
            if verbose:
                print(f"  ✓ Moomoo OpenD at {host}:{port}")
        else:
            if verbose:
                print(f"Step 1 — Moomoo OpenD at {host}:{port}")
            if not wait_for_opend(
                host, port, timeout_sec=timeout, on_wait=lambda: wait_message(host, port)
            ):
                print(f"Timed out after {timeout:.0f}s waiting for OpenD.", file=sys.stderr)
                return 1
            if verbose:
                print("  ✓ OpenD connected")
            else:
                print(f"  ✓ OpenD connected at {host}:{port}", flush=True)

        if strict or run_doctor:
            err = _verify_moomoo_ready(cfg)
            if err:
                print(f"  ✗ Moomoo broker not ready: {err}", file=sys.stderr)
                return 1
            if verbose:
                print("  ✓ Moomoo broker API ready (SPY bars)")

    if cfg.llm_provider == "ollama":
        if verbose:
            print("Step 2 — local Ollama LLM (no API key)")
        if not _openai_sdk_available():
            msg = "openai package missing — pip install -e \".[openai]\""
            print(f"  ✗ {msg}", file=sys.stderr)
            if strict:
                return 1
        elif ollama_reachable():
            if verbose:
                print("  ✓ Ollama already running")
        elif start_ollama_serve():
            if verbose:
                print("  ✓ Started ollama serve")
            else:
                print("  ✓ Ollama started", flush=True)
        else:
            msg = (
                "Ollama not running — install from https://ollama.com/download, "
                "then: ollama pull llama3.1 && ollama serve"
            )
            print(f"  ✗ {msg}", file=sys.stderr)
            if strict:
                return 1
        if strict and ollama_reachable() and not ollama_has_model(cfg.model):
            print(
                f"  ✗ Model {cfg.model!r} not found — run: ollama pull {cfg.model}",
                file=sys.stderr,
            )
            return 1
        if strict and ollama_reachable() and ollama_has_model(cfg.model) and verbose:
            print(f"  ✓ Ollama model {cfg.model} available")
    elif verbose:
        print(f"Step 2 — LLM provider: {cfg.llm_provider}")

    if run_doctor:
        if verbose:
            print("Step 3 — verify all systems")
        from aoa.health import run_connectivity_checks

        errors = run_connectivity_checks(cfg)
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        if errors:
            return 1
        if verbose:
            print("  ✓ Connectivity checks passed")
            print("\n=== All systems ready ===")
            print("  aoa run       — one analysis cycle (dry-run; no orders)")
            print("  aoa loop      — continuous cycles")
            print("  aoa serve     — web dashboard at http://127.0.0.1:8080")

    return 0
