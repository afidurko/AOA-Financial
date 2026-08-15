#!/usr/bin/env python3
"""Smoke the optional hftbacktest lane without live brokerage calls.

Requires::

    pip install -e ".[hftbacktest]"

Then::

    python examples/hftbacktest_smoke.py
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    from aoa.hftbacktest import HAS_HFTBACKTEST, probe_status, run_npz_smoke

    status = probe_status()
    print(json.dumps(status, indent=2))
    if not HAS_HFTBACKTEST:
        print('Install with: pip install -e ".[hftbacktest]"', file=sys.stderr)
        return 1
    result = run_npz_smoke(n_events=200, steps=15, seed=1)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
