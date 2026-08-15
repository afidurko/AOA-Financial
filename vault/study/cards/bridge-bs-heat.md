---
type: study-card
card_id: bridge-bs-heat
field: bridge
title: Black–Scholes ↔ heat equation
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# Black–Scholes ↔ heat equation

**Field:** `bridge` · **id:** `bridge-bs-heat`

## Statement

Under dS=μS dt+σS dW, a European claim satisfies the BS PDE; x=log S and τ=T−t (with discounting) reduce it to the heat equation.

## Proof sketch

1) Itô on V(S,t); impose driftless discounted portfolio ⇒ BS PDE.
2) Set x=ln S, τ=T−t, strip lower-order terms by exponential integrating factor.
3) Remaining operator is κ ∂xx − ∂τ. Solve with Gaussian kernel; transform back.

## Applications

- Closed-form calls/puts
- Greeks as heat-kernel sensitivities

## AOA mesh

Andrea/FinancePy context and options strategist inherit this map: vol = diffusion coefficient in the heat picture.

## Bridges

de-heat-fourier, phys-diffusion, econ-hjb

## Drill

Show how the Black–Scholes PDE reduces to the heat equation under log-price and time-to-maturity coordinates.
