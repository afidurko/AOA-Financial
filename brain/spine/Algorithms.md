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
- Mesh node `algo.hft_patterns` → educational pairs/maker/MA helpers (`aoa.research.hft_patterns`)
- Mesh node `algo.hftish_patterns` → educational OB imbalance helpers (`aoa.research.hftish_patterns`)

## HFT companion (reference only)

Sibling [afidurko/hft](https://github.com/afidurko/hft) documents classical
futures HFT strategies. Distilled Python helpers live in
`aoa.research.hft_patterns` (no broker calls). Study bridge:
`bridge-hft-spread`. Setup: `./scripts/hft-setup.sh` ·
[docs/how-to/hft-reference.md](../../docs/how-to/hft-reference.md).

## example-hftish companion (reference only)

Sibling [afidurko/example-hftish](https://github.com/afidurko/example-hftish)
documents Alpaca's 1¢ level-change / book-imbalance tick-taker. Distilled Python
helpers live in `aoa.research.hftish_patterns` (no broker calls). Julie/Morgan
inject `diagnose_snapshot_quote` into prompts; CLI `aoa hftish`. Study bridge:
`bridge-hftish-imbalance`. Setup: `./scripts/example-hftish-setup.sh` ·
[docs/how-to/example-hftish-reference.md](../../docs/how-to/example-hftish-reference.md).
