# HFT / microstructure research lane

AOA keeps several **offline** HFT and order-book tools as companions. None of
them replace the cash-account swarm (`aoa loop`) or submit live orders.

## In-tree (this repo)

| Lane | Module / CLI | Role |
|------|--------------|------|
| **hftbacktest** | `aoa.hftbacktest` · `aoa hft status\|smoke\|run` | Optional tick L2/L3 backtest (`pip install -e ".[hftbacktest]"`) |
| **HFT-Orderbook** | `aoa.orderbook` · `aoa hft book-smoke` | Vendored limit-order-book (add/cancel/execute locally) |
| **SGX LOB features** | `aoa.research.sgx_orderbook_patterns` | Rise ratio + weighted depth from SGX A50 notebooks |

Bridge: build a book with `LimitOrderBook`, then
`snapshot_from_limit_order_book` → `feature_vector` /
`depth_pressure_side`. See [sgx-orderbook-reference.md](sgx-orderbook-reference.md)
and [hftbacktest-integration.md](hftbacktest-integration.md).

```bash
python3 examples/sgx_orderbook_smoke.py
aoa hft book-smoke --json
```

## Sibling companions (clone beside the repo)

| Companion | Setup | Python ports | Guide |
|-----------|-------|--------------|-------|
| [SGX-Full-OrderBook-…](https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy) | `./scripts/sgx-orderbook-setup.sh` | `sgx_orderbook_patterns` | [sgx-orderbook-reference.md](sgx-orderbook-reference.md) |
| [hft](https://github.com/afidurko/hft) | `./scripts/hft-setup.sh` (when merged) | `hft_patterns` (pairs/maker/MA) | [hft-reference.md](hft-reference.md) |
| [example-hftish](https://github.com/afidurko/example-hftish) | `./scripts/example-hftish-setup.sh` (when merged) | `hftish_patterns` (1¢ imbalance follow) | [example-hftish-reference.md](example-hftish-reference.md) |
| [VisualHFT](https://github.com/afidurko/VisualHFT) | optional sibling | `aoa.visualhft` (when merged) | [visualhft-integration.md](visualhft-integration.md) |

Open PRs may land the `hft` / `example-hftish` / `VisualHFT` wiring; until then
the GitHub forks remain readable references. Mesh catalog:
`brain/mesh/repos.yaml`.

## How the pieces fit

```
SGX notebooks ──features──▶ sgx_orderbook_patterns
                                   ▲
aoa.orderbook (vendored LOB) ──────┘ snapshot_from_limit_order_book
                                   │
aoa.hftbacktest (optional) ── replay / latency research
example-hftish ── L1 imbalance / print-follow ideas
hft (C++) ── pairs bands / maker / MA ideas
VisualHFT ── VPIN / OTR / imbalance study ports
```

## Safety (Hard Floor)

- Offline / paper research only — never wire these into `Executor` without an
  explicit depth-feed design and human `AOA_LIVE_ACK`.
- Do not store exchange credentials in `brain/`, `vault/`, or companion clones
  used by loops.
- Deterministic cash guards in `src/aoa/risk/guards.py` stay binding for the
  live swarm path.
