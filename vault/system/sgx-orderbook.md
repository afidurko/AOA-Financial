---
tags: [type/system, companion, research, orderbook]
---

# SGX full order-book strategy (companion)

Sibling:
[afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy](https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy)
(fork of rorysroes — SGX A50 full LOB ML notebooks).

## Role in AOA

- **Reference only** — rise ratio + weighted depth feature ideas
- Python ports: `aoa.research.sgx_orderbook_patterns`
- Bridge: `snapshot_from_limit_order_book` → vendored `aoa.orderbook`
- Setup: `./scripts/sgx-orderbook-setup.sh`
- Guide: [docs/how-to/sgx-orderbook-reference.md](../../docs/how-to/sgx-orderbook-reference.md)
- Lane map: [docs/how-to/hft-research-lane.md](../../docs/how-to/hft-research-lane.md)

## Hard floor

Not an order path. No SGX credentials in vault. No live wiring.
