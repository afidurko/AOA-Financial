---
type: study-card
card_id: bridge-oqlb-shrink-bl-cvar
field: bridge
title: Ledoit–Wolf shrinkage ↔ Black–Litterman ↔ CVaR budgets
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Ledoit–Wolf shrinkage ↔ Black–Litterman ↔ CVaR budgets

**Field:** `bridge` · **id:** `bridge-oqlb-shrink-bl-cvar`

## Statement

LW shrinks sample ``Σ`` toward ``μI`` to stabilize tangency; Black–Litterman blends
equilibrium ``π=δΣw`` with views ``Pμ=Q``; CVaR risk budgets equalize tail-loss
contributions instead of variance contributions.

## Proof sketch

1) LW: ``Σ_shrunk=(1−ρ)S+ρ μI`` with analytic ``ρ∈[0,1]``.
2) BL posterior from ``(τΣ)^{-1}`` and ``P'Ω^{-1}P``; then tangency on ``μ_BL``.
3) Historical ES/CVaR tail average; damped multiplicative risk-budget updates.

## Applications

- ``aoa openquant compare`` shrinkage / BL / CVaR columns
- Andrea research overlays without live sizing

## AOA mesh

``ledoit_wolf_cov``, ``black_litterman_weights``, ``cvar_risk_budget_weights`` never
submit orders; research lane only.

## Bridges

bridge-oqlb-tangency-hrp, bridge-oqlb-risk-entropy

## Drill

Write the Black–Litterman equilibrium ``π=δΣw`` and name one reason to shrink ``Σ``.
