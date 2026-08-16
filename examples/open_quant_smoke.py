#!/usr/bin/env python3
"""Offline smoke: risk parity + transfer-entropy helpers (no brokerage)."""

from __future__ import annotations

from aoa.research.open_quant_patterns import (
    equal_risk_contribution,
    inverse_vol_weights,
    mutual_information_stats,
    net_information_flow,
    synthetic_smoke,
)


def main() -> None:
    smoke = synthetic_smoke(seed=7)
    cov = [[0.04, 0.005], [0.005, 0.01]]
    erc = equal_risk_contribution(cov)
    inv = inverse_vol_weights((0.20, 0.10))
    # Tiny deterministic series for MI printout
    xs = [0.1 * i for i in range(40)]
    ys = [0.08 * i + (0.02 if i % 2 else -0.02) for i in range(40)]
    mi = mutual_information_stats(xs, ys, bins=5)
    flow = net_information_flow(
        [0.0, 0.1, 0.2, 0.15, 0.3, 0.25, 0.4],
        [0.0, 0.05, 0.12, 0.18, 0.22, 0.35, 0.4],
        lags=1,
    )
    print(
        {
            "smoke_ok": smoke["ok"],
            "erc_weights": list(erc.weights),
            "inverse_vol": list(inv),
            "mutual_information": mi.mutual_information,
            "global_correlation": mi.global_correlation,
            "net_flow_dominant": flow.dominant,
            "offline_only": True,
        }
    )


if __name__ == "__main__":
    main()
