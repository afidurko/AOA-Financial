---
type: study-card
card_id: bridge-oqlb-networks-filter
field: bridge
title: MST / PMFG / partial-correlation market graphs
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# MST / PMFG / partial-correlation market graphs

**Field:** `bridge` · **id:** `bridge-oqlb-networks-filter`

## Statement

Correlation distance ``√((1−ρ)/2)`` yields an MST (``n−1`` edges); an approximate
PMFG keeps the strongest edges up to the planar bound ``3(n−2)``; partial
correlations from ``Σ^{-1}`` isolate direct links after conditioning on the rest.

## Proof sketch

1) MST: Kruskal on correlation distance.
2) PMFG-lite: sort ``|ρ|`` desc, keep ``≤3(n−2)`` edges.
3) Partial ``ρ_ij|rest = −Θ_ij/√(Θ_ii Θ_jj)`` with ``Θ=Σ^{-1}``.

## Applications

- Hub detection beyond raw threshold graphs
- Offline universe structure for study cards

## AOA mesh

``minimum_spanning_tree`` / ``planar_maximally_filtered_graph`` /
``partial_correlation_network`` — research-only.

## Bridges

bridge-oqlb-stylized-network, bridge-oqlb-risk-entropy

## Drill

State the MST edge count and the planar PMFG edge bound for ``n`` assets.
