---
type: study-card
card_id: bridge-as-reservation
field: bridge
title: Avellaneda–Stoikov reservation price ↔ inventory risk
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# Avellaneda–Stoikov reservation price ↔ inventory risk

**Field:** `bridge` · **id:** `bridge-as-reservation`

## Statement

A market maker's indifference (reservation) price skews linearly with inventory
and remaining horizon: `r = s − q γ σ² (T − t)`, with optimal half-spread
`(1/γ) log(1 + γ/k)` from exponential utility vs Poisson fills.

## Proof sketch

1) Mid follows diffusion `dS = σ dW`; inventory `q` is controlled by posted bid/ask.
2) Exponential utility + intensity `λ(δ)=A e^{−kδ}` ⇒ HJB for value `u(t,x,q,s)`.
3) Ansatz reduces to reservation price `r` and reservation spread independent of `q`.
4) Long inventory (`q>0`) lowers `r` so the ask is likelier / bid less aggressive.

## Applications

- Offline AS Monte-Carlo (`aoa avellaneda simulate`)
- Inventory-aware quote skew diagnostics for microstructure study

## AOA mesh

Julie may cite `aoa.avellaneda_stoikov` for reservation/skew math; sibling
`afidurko/avellaneda-stoikov` is reference-only — never an AOA order path.

## Bridges

bridge-ou-meanrev, econ-hjb, phys-diffusion

## Drill

Given mid `s`, inventory `q`, risk aversion `γ`, volatility `σ`, and time-to-horizon
`T−t`, write `r` and state how positive inventory moves the ask relative to flat.
