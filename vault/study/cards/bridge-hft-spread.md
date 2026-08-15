---
type: study-card
card_id: bridge-hft-spread
field: bridge
title: HFT pair mid-diff ↔ OU mean reversion
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# HFT pair mid-diff ↔ OU mean reversion

**Field:** `bridge` · **id:** `bridge-hft-spread`

## Statement

A trailing mean/std of main−hedge mid defines open bands (up/down = μ ± max(kσ, min_range) + fee). Open outside the band, exit when the diff returns to μ — discrete OU-style pairs control.

## Proof sketch

1) State X_t = mid_main − mid_hedge (simplearb map_vector).
2) Estimate μ, σ on a trailing window (CalParams).
3) Enter when X > μ+m or X < μ−m; HitMean closes when X crosses μ in the position's favor; outer stops at μ ± (1+λ)m.
4) Same structure as OU threshold policies with discrete samples.

## Applications

- Pairs / calendar spread research signals
- Hedged maker mid-diff thresholds (simplemaker)

## AOA mesh

Julie may cite aoa.research.hft_patterns for band/cross diagnostics; sibling afidurko/hft is reference-only — never an AOA order path.

## Bridges

bridge-ou-meanrev, de-lyapunov, phys-diffusion

## Drill

Given a trailing window of pair mid diffs, write the open bands and state the HitMean exit rule for long vs short.
