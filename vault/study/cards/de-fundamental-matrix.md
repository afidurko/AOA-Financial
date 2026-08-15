---
type: study-card
card_id: de-fundamental-matrix
field: de
title: Fundamental matrix for linear ODEs
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Fundamental matrix for linear ODEs

**Field:** `de` · **id:** `de-fundamental-matrix`

## Statement

For x'=A(t)x, a fundamental matrix Φ satisfies Φ'=AΦ and det Φ≠0; solutions are x=Φ c. For constant A, Φ(t)=exp(tA).

## Proof sketch

1) Columns of Φ are independent solutions ⇒ span the solution space.
2) Abel/Liouville: (det Φ)' = tr(A) det Φ ⇒ det never zero if nonzero once.
3) Variation of parameters for x'=Ax+g uses Φ∫ Φ^{-1}g.

## Applications

- Closed-form factor dynamics
- Impulse-response of linear signal filters

## AOA mesh

Multi-timeframe technical features are a linear filter bank; the fundamental matrix is the propagator of that filter.

## Bridges

de-heat-fourier, bridge-bs-heat

## Drill

Define a fundamental matrix. State Liouville's formula and how variation of parameters uses Φ.
