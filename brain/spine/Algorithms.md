---
tags: [type/spine, algorithms]
---

# Algorithms mesh

Julie owns algorithm clarity. Brain context injects into analysis via
`aoa.brain.context.brain_context_for_algorithms()`.

## Linked nodes

- Mesh node `algo.julie` → team Julie
- Mesh node `algo.signal_adapter` → plasticity / adapt path
- Mesh node `algo.swarm` → trading Orchestrator
- Mesh node `algo.sgx_orderbook_patterns` → LOB rise/depth helpers (`aoa.research.sgx_orderbook_patterns`)
- Mesh node `algo.hftish_patterns` → educational OB imbalance helpers (`aoa.research.hftish_patterns`)

## SGX order-book companion (reference only)

Sibling [afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy](https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy)
documents full-LOB feature engineering (rise ratio, weighted depth) and
sklearn model selection on SGX A50 ticks. Distilled Python helpers live in
`aoa.research.sgx_orderbook_patterns` (no broker calls); bridge from the
vendored LOB via `snapshot_from_limit_order_book`. Study bridge:
`bridge-sgx-depth-rise`. Setup: `./scripts/sgx-orderbook-setup.sh` ·
[docs/how-to/sgx-orderbook-reference.md](../../docs/how-to/sgx-orderbook-reference.md) ·
[docs/how-to/hft-research-lane.md](../../docs/how-to/hft-research-lane.md).

## example-hftish companion (reference only)

Sibling [afidurko/example-hftish](https://github.com/afidurko/example-hftish)
documents Alpaca's 1¢ level-change / book-imbalance tick-taker. Distilled Python
helpers live in `aoa.research.hftish_patterns` (no broker calls). Julie/Morgan
inject `diagnose_snapshot_quote` into prompts; CLI `aoa hftish`. Study bridge:
`bridge-hftish-imbalance`. Setup: `./scripts/example-hftish-setup.sh` ·
[docs/how-to/example-hftish-reference.md](../../docs/how-to/example-hftish-reference.md).
