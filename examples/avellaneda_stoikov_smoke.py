#!/usr/bin/env python3
"""Smoke the Avellaneda–Stoikov research lane (offline, no broker)."""

from __future__ import annotations

from aoa.avellaneda_stoikov import probe_status, run_synthetic_smoke


def main() -> int:
    print(probe_status())
    result = run_synthetic_smoke(n_steps=80, n_sims=10, seed=1)
    print(result.to_dict())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
