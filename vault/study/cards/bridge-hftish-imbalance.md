---
type: study-card
card_id: bridge-hftish-imbalance
field: bridge
title: Order-book imbalance ↔ level-change follow
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 3
---
# Order-book imbalance ↔ level-change follow

**Field:** `bridge` · **id:** `bridge-hftish-imbalance`

## Statement

After both bid and ask jump onto a new 1¢ spread, a large print that hits the
ask (bid) with bid (ask) size ≥ 1.8× the far side is a discrete follow signal —
inventory-capped, lag-gated microstructure control.

## Proof sketch

1) State Q_t = (bid, ask, bid_size, ask_size). Level change when both prices move
   and ask−bid = 0.01.
2) Arm only if the prior spread was also 0.01 (penny-to-penny).
3) On a trade: require size ≥ 100 and timestamp ≥ quote_time + 50ms.
4) Follow ask when price = ask and bid_size > 1.8 ask_size (room under max shares);
   follow bid symmetrically when selling inventory.

## Applications

- Research signals for high-volume names with frequent 1¢ moves
- Inventory / pending-lot capacity checks before any hypothetical follow

## AOA mesh

Julie may cite aoa.research.hftish_patterns for imbalance diagnostics; sibling
afidurko/example-hftish is reference-only — never an AOA order path.

## Bridges

bridge-ou-meanrev, phys-diffusion, bridge-sdf-martingale

## Drill

Given two consecutive penny-spread quotes and a print on the ask, state whether
the follow signal is buy, sell, or flat and name the blocking gate if flat.
