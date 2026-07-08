"""One-step activation: wait for Moomoo OpenD, ensure local LLM, run doctor."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from shutil import which

DEFAULT_PROFILE = "moomoo"
_OLLAMA_VERSION_URL = "http://127.0.0.1:11434/api/version"


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


def ensure_profile() -> None:
    """Default to the moomoo profile when none is selected."""
    import os

    from aoa.config import load_env_files

    if not os.environ.get("AOA_PROFILE") and not os.environ.get("AOA_ENV"):
        os.environ["AOA_PROFILE"] = DEFAULT_PROFILE
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
