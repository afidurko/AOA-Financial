---
type: study-card
card_id: de-gronwall
field: de
title: Gronwall inequality
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Gronwall inequality

**Field:** `de` · **id:** `de-gronwall`

## Statement

If u(t) ≤ α + ∫_{t0}^t β(s)u(s) ds with β≥0, then u(t) ≤ α exp(∫_{t0}^t β).

## Proof sketch

1) Let R(t)=α+∫ β u. Then u≤R and R'=β u ≤ β R.
2) For R>0, (ln R)' ≤ β ⇒ ln R(t)−ln α ≤ ∫β ⇒ R≤α e^{∫β}.
3) Hence u≤α e^{∫β}. Discrete and differential forms follow similarly.

## Applications

- Continuous dependence on initial data
- Stability estimates for numerical schemes

## AOA mesh

Bounds how far conviction/trust can drift under noisy cycle shocks — use as a sanity envelope on plasticity updates.

## Bridges

de-picard, de-lyapunov

## Drill

State Gronwall's inequality and prove the integral form.
