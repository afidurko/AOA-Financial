# Help — related content

Companion repos and docs that help operate AOA Financial. None of these are
vendored into this tree; clone them beside the project (or use your fork) when
you need them.

## Agent harness (Slack + web)

| Resource | Role |
|----------|------|
| **[qm](https://github.com/afidurko/qm)** | Multiplayer agent harness for work — personal and shared scopes, Slack + web UI, crons, sandbox, and harness-agnostic agent loops (Pi, OpenCode, Codex, Claude Code). Upstream: [yc-software/qm](https://github.com/yc-software/qm). |

**In-system wiring:** set `AOA_QM_URL` for the dashboard **QM ↗** header link and
`/api/config`. Clone sibling with `./scripts/qm-setup.sh`. Vault note:
`vault/system/qm.md`. Full guide: [how-to/qm-integration.md](how-to/qm-integration.md).

```bash
./scripts/qm-setup.sh
export AOA_QM_URL=http://localhost:8081
aoa serve
```

## Market UI

| Resource | Role |
|----------|------|
| **[OpenStock](https://github.com/Open-Dev-Society/OpenStock)** | Sibling market dashboard (charts, watchlists). Link from the AOA header via `AOA_OPENSTOCK_URL`. |

Setup: [how-to/openstock-integration.md](how-to/openstock-integration.md).

## Engineering loop

| Resource | Role |
|----------|------|
| **[loop-engineering](https://github.com/afidurko/loop-engineering)** | Scaffold for daily triage, repair queue, and maker/checker skills used by `LOOP.md` / `aoa repair`. |

In-repo: [LOOP.md](../LOOP.md), [safety.md](safety.md), [how-to/fresh-clone.md](how-to/fresh-clone.md).

## Quant reference

| Resource | Role |
|----------|------|
| **[Finance](https://github.com/shashankvemuri/Finance)** | Reference library of quantitative finance Python programs (used in Tom’s knowledge context). |
| **[hft](https://github.com/afidurko/hft)** | C++ HFT futures strategies (pairs arb, hedged maker, MA cross) as a sibling reference. Pure-Python idea ports: `aoa.research.hft_patterns`. Upstream fork of [keyianpai/hft](https://github.com/keyianpai/hft). |
| **[hftbacktest](https://github.com/afidurko/hftbacktest)** | Optional offline L2/L3 tick backtest (`pip install -e ".[hftbacktest]"`). Not the same as the C++ sibling — see [hftbacktest-integration.md](how-to/hftbacktest-integration.md). |

**In-system wiring:** clone with `./scripts/hft-setup.sh` (gitignored sibling).
Vault note: `vault/system/hft.md`. Guide: [how-to/hft-reference.md](how-to/hft-reference.md).
Not an order path — research / Julie algorithm context only.

## Local model runtime (optional)

| Resource | Role |
|----------|------|
| **[waste](https://github.com/afidurko/waste)** | Weight-Aware Streaming Tensor Engine — run large models (e.g. Kimi K3) by streaming weights from NVMe. Upstream: [sqliteai/waste](https://github.com/sqliteai/waste). |

Useful when you want a local OpenAI-compatible inference path for agents without
fitting the full model in RAM.
