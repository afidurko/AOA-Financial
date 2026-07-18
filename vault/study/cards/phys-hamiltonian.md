---
type: study-card
card_id: phys-hamiltonian
field: physics
title: Hamiltonian phase-space dynamics
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# Hamiltonian phase-space dynamics

**Field:** `physics` · **id:** `phys-hamiltonian`

## Statement

With p=∂L/∂q̇ and H=p q̇−L, Hamilton's equations are q̇=∂H/∂p, ṗ=−∂H/∂q. H is conserved if ∂L/∂t=0.

## Proof sketch

1) Legendre transform L→H assumed regular (convex in q̇).
2) dH= q̇ dp − (∂L/∂q)dq − (∂L/∂t)dt; substitute EL ⇒ Hamilton form.
3) Ḣ=∂H/∂t, so autonomy ⇒ conservation of H.

## Applications

- Phase-space portraits for oscillators and regimes
- Symplectic integrators preserve qualitative structure

## AOA mesh

Cycle checkpoints are phase-space snapshots of the swarm state; meshing edits should be symplectic-like (structure-preserving), not arbitrary overwrites.

## Bridges

phys-lagrangian, econ-hjb, phys-noether

## Drill

Define the Hamiltonian via Legendre transform and derive Hamilton's equations.
