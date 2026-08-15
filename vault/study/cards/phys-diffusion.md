---
type: study-card
card_id: phys-diffusion
field: physics
title: Diffusion, Brownian motion, and Fokker–Planck
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# Diffusion, Brownian motion, and Fokker–Planck

**Field:** `physics` · **id:** `phys-diffusion`

## Statement

For dX=μ dt+σ dW, the density p satisfies the Fokker–Planck PDE p_t=−∂x(μ p)+½∂xx(σ² p).

## Proof sketch

1) Itô on f(X): df= (μ f'+½σ² f'')dt + σ f' dW.
2) Take expectations; integrate by parts against p ⇒ weak form of FP.
3) Stationary density balances drift and diffusion fluxes.

## Applications

- Option pricing kernels
- Hitting-time / stop-loss probabilities

## AOA mesh

Monte-Carlo simulator paths are discrete Itô; scenario stress is changing (μ,σ) and re-reading the Fokker–Planck mass in the tails.

## Bridges

de-heat-fourier, bridge-bs-heat, bridge-ou-meanrev

## Drill

Write the Fokker–Planck equation for dX=μ dt+σ dW and sketch the Itô-to-PDE derivation.
