---
type: study-card
card_id: de-heat-fourier
field: de
title: Heat equation via Fourier / Gaussian kernel
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# Heat equation via Fourier / Gaussian kernel

**Field:** `de` · **id:** `de-heat-fourier`

## Statement

u_t = κ u_xx on ℝ has solution u(·,t)=G_t * u0 with G_t(x)=(4πκt)^{-1/2} exp(-x²/(4κt)).

## Proof sketch

1) Fourier transform: û_t = −κ ξ² û ⇒ û(ξ,t)=û0(ξ)e^{-κξ²t}.
2) Inverse transform of e^{-κξ²t} is the Gaussian kernel G_t.
3) Convolution theorem ⇒ u=G_t*u0. Maximum principle ⇒ uniqueness.

## Applications

- Diffusive smoothing of noisy series
- Link to Black–Scholes after log-price change of variables

## AOA mesh

News/sentiment shocks diffuse across correlated names; kernel width ~ effective information half-life.

## Bridges

bridge-bs-heat, phys-diffusion

## Drill

Derive the fundamental solution of the heat equation on the line using Fourier transforms.
