---
type: study-card
card_id: de-lyapunov
field: de
title: Lyapunov stability for autonomous systems
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Lyapunov stability for autonomous systems

**Field:** `de` · **id:** `de-lyapunov`

## Statement

If V is C¹, positive definite near an equilibrium x*, and V̇≤0, then x* is stable; if V̇<0 (definite), it is asymptotically stable.

## Proof sketch

1) Stability: sublevel sets {V≤c} are positively invariant when V̇≤0; shrink c so the set sits in any neighborhood of x*.
2) Asymptotic: LaSalle or strict decrease ⇒ trajectories approach the largest invariant set in {V̇=0}, which is {x*} when V̇ is definite.

## Applications

- Prove mean-reversion equilibria are attracting
- Certify risk dampers do not oscillate unboundedly

## AOA mesh

Treat portfolio exposure error as state; design a Lyapunov-like penalty so risk guards drive the state toward the cash-feasible set.

## Bridges

bridge-ou-meanrev, econ-hjb

## Drill

Define Lyapunov stability vs asymptotic stability. Give the V / V̇ criteria and a one-line LaSalle idea.
