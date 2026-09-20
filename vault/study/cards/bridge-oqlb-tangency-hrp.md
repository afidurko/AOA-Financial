---
type: study-card
card_id: bridge-oqlb-tangency-hrp
field: bridge
title: Tangency Sharpe ↔ hierarchical risk parity
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Tangency Sharpe ↔ hierarchical risk parity

**Field:** `bridge` · **id:** `bridge-oqlb-tangency-hrp`

## Statement

The tangency portfolio maximizes Sharpe via ``w ∝ Σ^{-1}(μ − r_f)``, while HRP
allocates along a correlation-distance dendrogram so lower-variance clusters
receive more budget. Research allocators only — never AOA execution.

## Proof sketch

1) Unconstrained tangency: solve ``Σw = μ − r_f``, normalize; optional long-only clip.
2) HRP distance ``√((1−ρ)/2)``, single-linkage order, recursive bisection by cluster variance.
3) ERC equalizes risk contributions; HRP softens estimation error via hierarchy.

## Applications

- `aoa openquant compare`
- Andrea/Julie portfolio-research context

## AOA mesh

`aoa.research.open_quant_patterns` never calls a broker; sibling
afidurko/open-quant-live-book is reference-only.

## Bridges

bridge-oqlb-risk-entropy, bridge-sdf-martingale

## Drill

Write the unconstrained tangency solution and state how HRP uses cluster variance.
