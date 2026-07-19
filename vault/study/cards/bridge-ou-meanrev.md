---
type: study-card
card_id: bridge-ou-meanrev
field: bridge
title: Ornstein–Uhlenbeck ↔ mean reversion
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# Ornstein–Uhlenbeck ↔ mean reversion

**Field:** `bridge` · **id:** `bridge-ou-meanrev`

## Statement

dX=θ(μ−X)dt+σ dW is Gaussian, Markov, mean-reverting with E[X_t]=μ+(x0−μ)e^{-θt} and known variance envelope.

## Proof sketch

1) Integrating factor e^{θt}: d(e^{θt}X)=θμ e^{θt}dt + σ e^{θt}dW.
2) Integrate; take expectation ⇒ exponential pull to μ.
3) Itô isometry ⇒ Var→ σ²/(2θ). Lyapunov V=(x−μ)² gives asymptotic stability of the mean.

## Applications

- Pairs trading / residual z-scores
- Trust score pull-to-prior in plasticity

## AOA mesh

Symbol trust and low-rank signal adapters should OU-revert toward 0 unless reinforced — prevents runaway conviction from one lucky cycle.

## Bridges

de-lyapunov, phys-diffusion, de-picard

## Drill

Solve the OU SDE for the mean path and explain the stationary variance.
