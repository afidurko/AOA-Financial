---
type: study-card
card_id: bridge-sdf-martingale
field: bridge
title: SDF / risk-neutral martingale pricing
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# SDF / risk-neutral martingale pricing

**Field:** `bridge` · **id:** `bridge-sdf-martingale`

## Statement

No-arbitrage (FTAP) ⇔ existence of an equivalent measure Q under which discounted traded assets are martingales; prices are E^Q[payoff].

## Proof sketch

1) Define gains processes; NA ⇒ separating hyperplane ⇒ state prices.
2) Normalize to a probability Q∼P; discounted price = conditional expectation.
3) Complete markets ⇒ unique Q; incomplete ⇒ a convex set of Q's.

## Applications

- Derivative pricing consistency checks
- Detect static arbitrage in option chains

## AOA mesh

Options strategist must not propose structures that admit static arbitrage vs the chain; risk manager enforces cash feasibility on top.

## Bridges

bridge-bs-heat, econ-nash, econ-hjb

## Drill

State the First Fundamental Theorem of Asset Pricing and explain the role of the risk-neutral measure.
