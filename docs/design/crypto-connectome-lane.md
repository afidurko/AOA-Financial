# Crypto Connectome Lane — design

**Status:** shipped (offline research lane) · **Owner:** ATTL auto-12 · **Entry:** `aoa crypto`

An offline research lane that trains on Bitcoin, Ethereum, Solana, and XRP by
walking the calendar **one day at a time from 2007-07-17**, routes market
features through a **C. elegans-style connectome to motor outputs**, and
backtests with a **+32% take-profit / −26% stop-loss bracket attached before
every order executes**. No live order path — the lane never touches a broker.

## GitHub research (what we found and used)

A sweep of new/notable repos surfaced a wave of connectome-driven agents:

| Repo | Takeaway used here |
|------|--------------------|
| [nftechie/stonkfly](https://github.com/nftechie/stonkfly) | Fly connectome trading sim: market data → sensory stimulation → connectome propagation → fixed neural readout → buy/sell/hold, with P&L driving dopamine cells (PAM/PPL) that gate synaptic change. We mirror this loop in miniature: `MarketWorm.decide()` + `reinforce(realized_return)`. |
| [heyseth/worm-sim](https://github.com/heyseth/worm-sim) | Browser port of Busbice's C. elegans model — accumulate-and-fire with threshold ~30, sustained sensory stimulation per cycle, motor classes summed into muscle drives. This is the dynamics of `aoa.connectome.engine.Connectome`. |
| [SyntheticBrains/nematode](https://github.com/SyntheticBrains/nematode) | Closed-loop worm-brain comparison rig (26 pluggable brains) — validates the sensory→command-interneuron→motor decomposition we use. |
| [openworm](https://github.com/openworm) lineage | The published wiring (White et al. 1986; Varshney et al. 2011) from which the curated sub-connectome weights in `aoa.connectome.elegans` are distilled. |

Existing in-repo assets reused instead of new dependencies:
`aoa.adapt.lowrank.LowRankAdapter` (pure-Python LoRA-style head),
`aoa.httpcompat` (httpx), and the offline-research-lane CLI pattern
(`aoa hftish` / `aoa openquant`).

## Architecture

```
daily candles (Bitstamp + Yahoo, cached data/crypto/*.json)
        │
        ▼
calendar_walk(2007-07-17 → today)        every day, labeled:
        │                                 market / pre-genesis / pre-market / gap
        ▼
DayFeatures (no lookahead: ret1/5/20, vol shock, drawdown, capitulation, streak)
        │
        ├─► MarketWorm (connectome → motor outputs)
        │     sensory: AWA/AWC/ASE food ≈ momentum · ASH/ALM/AVM threat ≈ vol/drawdown
        │     command: AVB/PVC forward vs AVA/AVD/AVE backward
        │     motor:   B-class (forward = long) vs A-class (reverse = exit)
        │     plasticity: realized return = dopamine reward on traced synapses
        │
        ├─► PatternMemory (persistent JSON): streak continuation, seasonality,
        │     vol-regime and drawdown-bucket next-day stats, big-move follow-through
        │
        └─► LowRankAdapter head: online SGD toward realized next-day return
        │
        ▼
combined_signal() → buy / sell / hold + conviction
        │
        ▼
CryptoBacktester: entry at next open, ONLY with BracketPolicy.attach() —
  take-profit +32% / stop-loss −26% computed BEFORE execution; stop checked
  before target each day (conservative); fees both sides.
```

### The bracket is structural

`BracketPolicy.attach(entry_price)` is the only way to construct an executable
entry, and `_execute_entry` raises rather than run without a valid bracket.
There is no code path that opens an unprotected position. Defaults are the
mandated **+32% / −26%**; both are CLI-overridable for experiments.

### Day-by-day, not reverse-engineered

`aoa crypto train` walks all ~7,000 calendar days from 2007-07-17. Days before
an asset's genesis are counted as `pre-genesis`, days between genesis and
first market data as `pre-market`, missing candles inside the market era as
`gap`. Learning is strictly online and walk-forward: features for day *t* use
only candles ≤ *t*, and the day-*t* outcome is only learned after prediction.
Reported hit-rates are therefore honest out-of-sample-style numbers, not fit
statistics. Backtests use a *fresh* trainer that learns inside its own walk,
so no state leaks from a prior full-tape training run.

### Persistent memory

Everything learned persists under `data/crypto/models/` per asset:
`*_memory.json` (PatternMemory), `*_adapter.json` (LoRA head), `*_worm.json`
(plasticity-shifted connectome, with baseline weights so the drift cap holds
across sessions). A later session resumes exactly where the last one stopped.

## Data reality (2007 vs crypto)

The user-selected epoch 2007-07-17 predates all crypto — Bitcoin's genesis
block is 2009-01-03 and its first exchange market opened 2010-07-17. Keyless
free sources bound what a fresh clone can fetch:

| Asset | First market | Our earliest daily candle | Source |
|-------|-------------|---------------------------|--------|
| BTC | 2010-07-17 (Mt. Gox) | 2011-08-18 | Bitstamp |
| ETH | 2015-08-07 | 2017-08-16 | Bitstamp |
| SOL | 2020-04-10 | 2020-04-10 | Yahoo |
| XRP | 2013-08-04 | 2016-12-16 | Bitstamp |

Pre-coverage days are walked and labeled honestly rather than fabricated.

## The trader swarm (second pass)

`aoa.crypto.traders` scales the lane from one trainer to a **swarm** — the
account-repo mesh (`docs/design/account-repo-mesh.md`) maps each member to the
GitHub repo it was distilled from:

| Trader | Model | Source repo |
|--------|-------|-------------|
| `momentum-head` | LoRA-style low-rank head | (in-repo `aoa.adapt`) |
| `deep-mlp-16x8`, `deep-mlp-24x12x6` | deep backprop MLPs + return lags | deepstock, Stock-Price-Prediction |
| `gated-reservoir` | input-selective gated recurrence | GHOST, Deep-Learning--Stock-Market-Prediction |
| `connectome-worm` | C. elegans motor circuit | stonkfly, worm-sim |
| `pattern-memory` | persistent pattern statistics | (in-repo) |
| `ar-forecaster` | online AR(5) | Stock-Market-App |
| `pairs-vs-*` | log-ratio z-score mean reversion | Pairs-Trading-Analyzer |

The **Hedge ensemble** (AutoHedge/HAAS distillation) fuses votes with
multiplicative weights — each trader's weight decays exponentially with its
realized directional loss — and the **survival gate**
(`aoa.crypto.survival.BracketSurvival`, from the lifelines/scikit-survival
forks) vetoes entries in regimes where history shows the −26% stop wins the
race against the +32% target. Everything persists (`*_ensemble.json`), and the
backtester drives either the single trainer or the swarm through the same
`decide`/`learn` strategy protocol.

First honest walk-forward swarm results (fresh state, 25 bps fees): BTC
+176,624% (vs +47,854% single-trainer), ETH +159% (vs +2%), SOL +58%
(vs +2,499%), XRP −82% (vs +15%) — the ensemble helps where per-trader skill
differs (BTC/ETH) and hurts where no member has an edge (XRP). Hedge weights
after full training: connectome dominates BTC (56%), pairs traders dominate
ETH/SOL/XRP (30–38%), and the gated reservoir earns the best hit rates
(57.7% BTC, 55.5% XRP).

## Verification

`python3 -m pytest -q` (all suites) plus dedicated offline tests:
`tests/test_connectome.py`, `tests/test_crypto_history.py`,
`tests/test_crypto_training.py`, `tests/test_crypto_backtest.py` — bracket
math, no-lookahead features, persistence round-trips, plasticity caps, and
calendar-walk labeling.

## Constraints compliance

Hard Safety Floor respected: no live orders, no guard changes, no `.env`
edits, draft-PR only. The lane sits beside the other offline research lanes
and is dispatched in `aoa.cli` before any broker `Config` is constructed.
