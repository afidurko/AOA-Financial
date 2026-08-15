#!/usr/bin/env python3
"""Smoke the VisualHFT research lane (offline synthetic tape)."""

from __future__ import annotations

import json

from aoa.visualhft import probe_status, run_synthetic_smoke


def main() -> int:
    print("status:", json.dumps(probe_status(), indent=2))
    result = run_synthetic_smoke(n_trades=150, seed=42)
    print("smoke:", json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
