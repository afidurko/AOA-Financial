---
type: study-card
card_id: econ-hjb
field: econ
title: Hamilton–Jacobi–Bellman equation
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 4
---
# Hamilton–Jacobi–Bellman equation

**Field:** `econ` · **id:** `econ-hjb`

## Statement

In continuous time, 0=max_a { r(x,a) + ∇V·μ(x,a) + ½ tr(σσᵀ Hess V) } − δ V (plus boundary terms), the infinitesimal Bellman equation.

## Proof sketch

1) Discrete DP over dt, expand V(x+dx) by Itô.
2) Divide by dt, send dt→0 ⇒ HJB.
3) Viscosity solutions handle nonsmooth V; verification theorems recover optimality when a classical solution exists.

## Applications

- Merton portfolio problem
- Optimal execution with diffusion prices

## AOA mesh

Options strategist + portfolio manager approximate a constrained HJB: maximize expected utility subject to cash-account σ-structure.

## Bridges

econ-bellman, phys-hamiltonian, phys-diffusion, bridge-bs-heat

## Drill

Derive the HJB equation from discrete dynamic programming plus Itô's lemma.
