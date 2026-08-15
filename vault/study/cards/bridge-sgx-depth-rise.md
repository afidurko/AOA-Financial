---
type: study-card
card_id: bridge-sgx-depth-rise
field: bridge
title: LOB depth imbalance ↔ short-horizon rise
mastery: 0.0
last_reviewed: ''
due_at: ''
bridges_count: 2
---
# LOB depth imbalance ↔ short-horizon rise

**Field:** `bridge` · **id:** `bridge-sgx-depth-rise`

## Statement

On a multi-level limit order book, weighted ask vs bid size
`(W_a − W_b)/(W_a + W_b)` measures instantaneous pressure, while a trailing
rise ratio `(p_t − p_{t−Δ})/p_{t−Δ}` measures recent mid/ask drift. Agreeing
signs are a classical short-horizon microstructure cue (SGX A50 notebook
pipeline); disagreement is noise.

## Proof sketch

1) Depth weights aggregate displayed liquidity; imbalance ∈ (−1, 1).
2) Rise ratio is a discrete log-return proxy over a fixed clock window.
3) A forward “tradeable” label (bid &gt; min ask over horizon) is a research
   hit-rate target — not an executable fill model under AOA cash constraints.

## Applications

- Offline LOB feature engineering beside `aoa.orderbook` / VisualHFT lanes
- Julie algorithm clarity for microstructure study cards

## AOA mesh

Research helpers in `aoa.research.sgx_orderbook_patterns` never call a broker;
swarm remains bar/L1 based. Use as context for Julie, not as an execute stage.

## Bridges

bridge-ou-meanrev, bridge-sdf-martingale

## Drill

Define weighted depth imbalance and rise ratio; explain why AOA treats a
forward bid-lifts-ask label as research-only.
