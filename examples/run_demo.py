#!/usr/bin/env python3
"""End-to-end demonstration of the AOA-Financial engine.

Builds a database, ingests a handful of names with full history back to 1960,
runs the complete analysis + swarm stack, and prints a ranked decision table.

    python examples/run_demo.py
"""
import os
import sys

# Make the package importable when run from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aoa_financial.config import Config
from aoa_financial.databases.store import MarketStore
from aoa_financial.ingest.loaders import ingest_ticker
from aoa_financial.analysis.reverse_engineer import reverse_engineer
from aoa_financial.swarm.decision import analyze_ticker

UNIVERSE = ["AAPL", "MSFT", "XOM", "JPM", "KO", "BA"]


def main() -> int:
    config = Config(data_dir=".aoa_demo")
    config.ensure_dirs()
    print("AOA-Financial — end-to-end demo")
    print("=" * 70)

    with MarketStore(config.db_path) as store:
        decisions = []
        for t in UNIVERSE:
            r = ingest_ticker(store, t)
            sec = store.get_security(t)
            first = sec.listed_on if sec else "?"
            print(f"ingested {t:5s}: {r['bars']:>6,} bars since {first} "
                  f"[{r['sector']}] via {r['source']}")
            decisions.append(analyze_ticker(store, t, config=config, run_id="demo"))

        # Spotlight one reverse-engineering report.
        print("\n" + "=" * 70)
        print("Reverse-engineering spotlight: AAPL")
        print("=" * 70)
        res = reverse_engineer("AAPL", store.get_bars("AAPL"),
                               stored_sentiment=store.latest_sentiment("AAPL"))
        for line in res.inferences:
            print("  •", line)

        print("\n" + "=" * 70)
        print("Swarm decision ranking")
        print("=" * 70)
        decisions.sort(key=lambda d: d.conviction, reverse=True)
        print(f"{'TICKER':8s}{'ACTION':7s}{'CONV':>7s}{'CONF':>7s}{'WEIGHT':>8s}")
        for d in decisions:
            print(f"{d.ticker:8s}{d.action:7s}{d.conviction:>+7.2f}"
                  f"{d.confidence:>7.0%}{d.target_weight:>8.1%}")
    print(f"\nPersisted to {config.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
