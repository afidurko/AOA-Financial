#!/usr/bin/env python3
"""Print a visual checklist for Moomoo setup stages A, B, or C."""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and key not in __import__("os").environ:
            __import__("os").environ[key] = val.strip()


def _opend_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _box(title: str, lines: list[str]) -> str:
    width = max(len(title), *(len(x) for x in lines), 52)
    bar = "═" * (width + 2)
    out = [f"╔{bar}╗", f"║ {title.ljust(width)} ║", f"╠{bar}╣"]
    for line in lines:
        out.append(f"║ {line.ljust(width)} ║")
    out.append(f"╚{bar}╝")
    return "\n".join(out)


STAGES = {
    "a": {
        "name": "Stage A — Live data (no orders)",
        "env": {"AOA_ENV": "paper-dry", "AOA_DRY_RUN": "true", "MOOMOO_LIVE": "false"},
        "goal": "Real quotes/bars · agents analyze · NO orders submitted",
    },
    "b": {
        "name": "Stage B — Paper trading (simulate orders)",
        "env": {"AOA_ENV": "paper", "AOA_DRY_RUN": "false", "MOOMOO_LIVE": "false"},
        "goal": "Orders go to Moomoo SIMULATE account (fake money)",
    },
    "c": {
        "name": "Stage C — Live trading (real money)",
        "env": {
            "AOA_ENV": "live",
            "AOA_DRY_RUN": "false",
            "MOOMOO_LIVE": "true",
            "AOA_LIVE_ACK": "I_UNDERSTAND",
        },
        "goal": "REAL money · requires MOOMOO_UNLOCK_PASSWORD",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=["a", "b", "c", "A", "B", "C"],
        help="Setup stage to check (a=live data, b=paper, c=live)",
    )
    args = parser.parse_args()
    stage_key = args.stage.lower()
    stage = STAGES[stage_key]

    _load_dotenv()
    import os

    sys.path.insert(0, str(ROOT / "src"))
    try:
        from aoa.config import Config

        cfg = Config.from_env(load_dotenv=False)
    except Exception as exc:  # pragma: no cover - friendly CLI
        print(f"Could not load config: {exc}", file=sys.stderr)
        return 1

    host = os.environ.get("MOOMOO_OPEND_HOST", cfg.moomoo_opend_host)
    port = int(os.environ.get("MOOMOO_OPEND_PORT", cfg.moomoo_opend_port))
    opend_ok = _opend_reachable(host, port)
    def _cfg_val(key: str) -> str:
        mapping = {
            "AOA_ENV": str(cfg.env),
            "AOA_DRY_RUN": "true" if cfg.dry_run else "false",
            "MOOMOO_LIVE": "true" if cfg.moomoo_live else "false",
            "AOA_LIVE_ACK": "I_UNDERSTAND" if cfg.live_acknowledged else "",
        }
        return os.environ.get(key, mapping.get(key, ""))

    env_ok = all(_cfg_val(k) == v for k, v in stage["env"].items() if k != "AOA_LIVE_ACK")
    if stage_key == "c":
        env_ok = env_ok and _cfg_val("AOA_LIVE_ACK") == "I_UNDERSTAND"
        env_ok = env_ok and bool(cfg.moomoo_unlock_password)
    anthropic_ok = bool(cfg.anthropic_api_key and cfg.anthropic_api_key.startswith("sk-"))
    pkg_ok = (ROOT / "src" / "aoa").is_dir()
    env_file_ok = (ROOT / ".env").is_file()

    checks = [
        ("AOA package present", pkg_ok, "pip install -e \".[dev,web]\""),
        (".env file exists", env_file_ok, "cp .env.example .env"),
        ("ANTHROPIC_API_KEY set", anthropic_ok, "Edit .env — add sk-ant-... key"),
        (
            f"OpenD reachable at {host}:{port}",
            opend_ok,
            "Install OpenD, log in, keep app running",
        ),
        (f".env matches {stage_key.upper()} settings", env_ok, "See docs/how-to/moomoo-setup-walkthrough.md"),
    ]

    print()
    print(_box(stage["name"], [stage["goal"], ""]))
    print()
    print("Checklist")
    print("─────────")
    all_ok = True
    for label, ok, fix in checks:
        mark = "✓" if ok else "✗"
        print(f"  {mark}  {label}")
        if not ok:
            print(f"      → {fix}")
            all_ok = False

    print()
    if all_ok:
        print("All checks passed. Next:")
        if stage_key == "a":
            print("  python3 -m aoa.cli doctor")
            print("  python3 -m aoa.cli run")
        elif stage_key == "b":
            print("  python3 -m aoa.cli doctor   # should show simulate")
            print("  python3 -m aoa.cli run      # orders → simulate account")
        else:
            print("  python3 -m aoa.cli doctor   # should show live")
            print("  python3 -m aoa.cli run      # REAL orders — be careful")
    else:
        print("Complete the ✗ items above, then re-run:")
        print(f"  python3 scripts/moomoo_setup_stage.py {stage_key}")
    print()
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
