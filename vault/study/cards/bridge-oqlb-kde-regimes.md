---
type: study-card
card_id: bridge-oqlb-kde-regimes
field: bridge
title: KDE entropy ↔ rolling stylized regimes
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# KDE entropy ↔ rolling stylized regimes

**Field:** `bridge` · **id:** `bridge-oqlb-kde-regimes`

## Statement

Silverman-bandwidth Gaussian KDE estimates differential entropy / MI without
histogram bins; rolling stylized facts label regimes (``fat_tails`` /
``vol_cluster`` / ``calm`` / ``mixed``) for Julie snapshot context.

## Proof sketch

1) ``h*=1.06 σ n^{-1/5}``; ``f̂`` via Gaussian kernel; ``H=−∫f̂ log f̂``.
2) ``I(X;Y)=H(X)+H(Y)−H(X,Y)`` on a product grid.
3) Roll window ``stylized_facts``; fraction of fat-tail / vol-cluster windows → regime.

## Applications

- Julie ``snapshot_research_context`` regime fields
- Offline MI when bins are unstable

## AOA mesh

``kde_mutual_information_stats`` / ``stylized_regime_summary`` are research diagnostics.

## Bridges

bridge-oqlb-stylized-network, bridge-oqlb-risk-entropy

## Drill

State Silverman's bandwidth formula and how a rolling regime label is chosen.
