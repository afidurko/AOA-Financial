---
type: study-card
card_id: econ-bellman
field: econ
title: Bellman principle / dynamic programming
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# Bellman principle / dynamic programming

**Field:** `econ` · **id:** `econ-bellman`

## Statement

V(x)=max_a { r(x,a) + γ E[V(x')|x,a] }. Optimal policies solve this fixed point under contraction of the Bellman operator (γ<1).

## Proof sketch

1) Principle of optimality: suffixes of optimal plans are optimal.
2) Bellman operator T is a γ-contraction on bounded functions.
3) Banach ⇒ unique V*; policy improvement / value iteration converge.

## Applications

- Discrete trading/inventory problems
- When to realize gains vs hold under costs

## AOA mesh

Each swarm cycle is one DP stage; plasticity lessons approximate value-shaping bonuses from past realizations.

## Bridges

econ-hjb, econ-kuhn-tucker, de-picard

## Drill

Write the Bellman equation. Why is the Bellman operator a contraction?
