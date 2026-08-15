# HFT / microstructure research lane

AOA keeps several **offline** HFT and order-book tools as companions. None of
them replace the cash-account swarm (`aoa loop`) or submit live orders.

## In-tree (this repo)

| Lane | Module / CLI | Role |
|------|--------------|------|
| **hftbacktest** | `aoa.hftbacktest` · `aoa hft status\|smoke\|run` | Optional tick L2/L3 backtest (`pip install -e ".[hftbacktest]"`) |
| **HFT-Orderbook** | `aoa.orderbook` · `aoa hft book-smoke` | Vendored limit-order-book (add/cancel/execute locally) |
| **SGX LOB features** | `aoa.research.sgx_orderbook_patterns` | Rise ratio + weighted depth from SGX A50 notebooks |
| **example-hftish** | `aoa.research.hftish_patterns` · `aoa hftish` | 1¢ level-change / book-imbalance follow ideas |
| **VisualHFT studies** | `aoa.visualhft` · `aoa visualhft` | Offline LOB imbalance, VPIN, OTR study ports |

Bridge SGX features onto the vendored book with
`snapshot_from_limit_order_book` → `feature_vector` /
`depth_pressure_side`. See [sgx-orderbook-reference.md](sgx-orderbook-reference.md)
and [hftbacktest-integration.md](hftbacktest-integration.md).

```bash
python3 examples/sgx_orderbook_smoke.py
aoa hft book-smoke --json
aoa hftish status
aoa visualhft status
```

## Sibling clones (optional, beside the repo)

| Companion | Setup | Guide |
|-----------|-------|-------|
| [SGX-Full-OrderBook-…](https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy) | `./scripts/sgx-orderbook-setup.sh` | [sgx-orderbook-reference.md](sgx-orderbook-reference.md) |
| [example-hftish](https://github.com/afidurko/example-hftish) | `./scripts/example-hftish-setup.sh` | [example-hftish-reference.md](example-hftish-reference.md) |
| [VisualHFT](https://github.com/afidurko/VisualHFT) | `./scripts/visualhft-setup.sh` | [visualhft-integration.md](visualhft-integration.md) |
| [hft](https://github.com/afidurko/hft) | `./scripts/hft-setup.sh` | [hft-reference.md](hft-reference.md) · `aoa.research.hft_patterns` |

Mesh catalog: `brain/mesh/repos.yaml`. Multi-root Cursor folders:
`./scripts/write-aoa-workspace.sh` · [workspace-mesh.md](workspace-mesh.md).

## How the pieces fit

```
SGX notebooks ──features──▶ sgx_orderbook_patterns
                                   ▲
aoa.orderbook (vendored LOB) ──────┘ snapshot_from_limit_order_book
                                   │
aoa.hftbacktest (optional) ── replay / latency research
example-hftish ── L1 imbalance / print-follow ideas
VisualHFT ── VPIN / OTR / imbalance study ports
hft (C++) ── pairs bands / maker / MA ideas (optional sibling)
```

## Safety (Hard Floor)

- Offline / paper research only — never wire these into `Executor` without an
  explicit depth-feed design and human `AOA_LIVE_ACK`.
- Do not store exchange credentials in `brain/`, `vault/`, or companion clones
  used by loops.
- Deterministic cash guards in `src/aoa/risk/guards.py` stay binding for the
  live swarm path.
