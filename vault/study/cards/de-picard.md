---
type: study-card
card_id: de-picard
field: de
title: Picard–Lindelöf existence and uniqueness
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Picard–Lindelöf existence and uniqueness

**Field:** `de` · **id:** `de-picard`

## Statement

If f is Lipschitz in y (uniformly in t on a rectangle) and continuous in t, the IVP y'=f(t,y), y(t0)=y0 has a unique local solution.

## Proof sketch

1) Rewrite as integral equation y = T[y] = y0 + ∫_{t0}^t f(s,y(s)) ds.
2) On a small ball in C([t0,t0+h]), T is a contraction (Lipschitz + small h).
3) Banach fixed-point ⇒ unique fixed point = unique local solution.
4) Continuability: extend until the graph exits every compact set.

## Applications

- ODE well-posedness for mean-reverting signals
- Unique filter trajectories given Lipschitz updates

## AOA mesh

Plasticity trust updates and signal adapters must be Lipschitz-bounded so online learning has a unique trajectory per cycle history.

## Bridges

bridge-ou-meanrev, de-gronwall

## Drill

State Picard–Lindelöf. Outline the contraction-mapping proof and what fails without a Lipschitz condition.
