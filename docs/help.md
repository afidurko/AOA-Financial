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
| **[VisualHFT](https://github.com/afidurko/VisualHFT)** | Live Level-2 microstructure desktop app (Windows/.NET). AOA ports LOB imbalance, VPIN, and OTR offline via `aoa visualhft`. |

Setup: [how-to/openstock-integration.md](how-to/openstock-integration.md) ·
[how-to/visualhft-integration.md](how-to/visualhft-integration.md).

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
| **[example-hftish](https://github.com/afidurko/example-hftish)** | Alpaca order-book imbalance tick-taker (1¢ level changes + size imbalance). Pure-Python idea ports: `aoa.research.hftish_patterns`. Upstream fork of [alpacahq/example-hftish](https://github.com/alpacahq/example-hftish). |
| **[SGX-Full-OrderBook-…](https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy)** | SGX A50 full LOB ML notebooks (rise ratio, weighted depth). Pure-Python idea ports: `aoa.research.sgx_orderbook_patterns`. |

**In-system wiring:** clone with `./scripts/hft-setup.sh` or
`./scripts/example-hftish-setup.sh` (gitignored siblings). Vault notes:
`vault/system/hft.md`, `vault/system/example-hftish.md`. Guides:
[how-to/hft-reference.md](how-to/hft-reference.md),
[how-to/example-hftish-reference.md](how-to/example-hftish-reference.md).
Not an order path — research / Julie algorithm context only.

## Local model runtime (optional)

| Resource | Role |
|----------|------|
| **[waste](https://github.com/afidurko/waste)** | Weight-Aware Streaming Tensor Engine — run large models (e.g. Kimi K3) by streaming weights from NVMe. Upstream: [sqliteai/waste](https://github.com/sqliteai/waste). |

Useful when you want a local OpenAI-compatible inference path for agents without
fitting the full model in RAM.

## Market microstructure (research)

| Resource | Role |
|----------|------|
| **[avellaneda-stoikov](https://github.com/afidurko/avellaneda-stoikov)** | Classic AS HFT market-making simulation + paper PDFs. AOA ports the math as an offline lane: `aoa avellaneda status|smoke|simulate`. |
| **[VisualHFT](https://github.com/afidurko/VisualHFT)** | Live L2 desktop + `aoa visualhft` study ports (LOB imbalance, VPIN, OTR). |
| **[hftbacktest](https://github.com/afidurko/hftbacktest)** | Optional tick L2/L3 engine + vendored LOB via `aoa hft`. |

Mesh status for every lane: `aoa microstructure status`.
Guide: [how-to/microstructure-lanes.md](how-to/microstructure-lanes.md) ·
[how-to/avellaneda-stoikov.md](how-to/avellaneda-stoikov.md).
Never an order path — Hard Safety Floor still applies.
