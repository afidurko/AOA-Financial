---
type: study-card
card_id: bridge-oqlb-stylized-network
field: bridge
title: Stylized facts ↔ correlation networks
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Stylized facts ↔ correlation networks

**Field:** `bridge` · **id:** `bridge-oqlb-stylized-network`

## Statement

Fat tails (excess kurtosis) and volatility clustering (``|r|`` ACF ≫ ``r`` ACF)
are classical stylized facts; thresholding ``|ρ|`` builds a market graph whose
degree centrality flags hub names.

## Proof sketch

1) Sample skew/kurtosis on log returns; ACF(1) on ``r`` vs ``|r|``.
2) Edge ``(i,j)`` iff ``|ρ_ij| ≥ θ``; centrality = deg/(n−1).
3) Research diagnostics only — not an AOA order trigger.

## Applications

- Julie `snapshot_research_context` from daily bars
- Universe hub detection for study cards

## AOA mesh

Julie/Andrea may cite open-quant stylized facts; never an order path.

## Bridges

bridge-oqlb-risk-entropy, phys-diffusion

## Drill

Define excess kurtosis and explain why ``|r|`` ACF detects clustering better than raw return ACF.
