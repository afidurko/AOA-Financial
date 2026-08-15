---
type: study-card
card_id: econ-kuhn-tucker
field: econ
title: Karush–Kuhn–Tucker conditions
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Karush–Kuhn–Tucker conditions

**Field:** `econ` · **id:** `econ-kuhn-tucker`

## Statement

For min f(x) s.t. g(x)≤0, h(x)=0 (constraint qualifications), optima satisfy ∇f+λ∇g+μ∇h=0, λ≥0, λ·g=0, primal feasibility.

## Proof sketch

1) Form Lagrangian L=f+λg+μh.
2) Under LICQ/MFCQ, no feasible descent direction ⇒ stationarity.
3) Complementary slackness: inactive inequalities have λ_i=0.
4) Sufficiency under convexity of f and g.

## Applications

- Consumer/producer problems with inequality constraints
- Portfolio caps and cash buffers as KKT inequalities

## AOA mesh

Deterministic risk guards are primal constraints; rejected proposals are complementary-slackness failures (λ>0 on the binding cap).

## Bridges

phys-lagrangian, econ-bellman

## Drill

State the KKT conditions. Explain complementary slackness with a single inequality constraint.
