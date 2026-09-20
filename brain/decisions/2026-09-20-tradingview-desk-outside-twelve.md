# Decision: TradingView desk sub-team outside the ATTL twelve

**Date:** 2026-09-20
**Status:** Accepted (human has final say on every proposal)
**Related:** Riley quant desk outside twelve; Jim/Cindy specialists outside twelve

## Decision

Add a **TradingView desk** — five deterministic desk members **outside**
`TWELVE_MEMBER_ROSTER`, led by **Julie** (algorithm specialist), risk sign-off
**Andrea**, critical-only review **Kai**:

| Member | Owns |
|--------|------|
| Dara   | candles (Yahoo / Kraken / Coinbase), 2000-stock US universe, fundamentals snapshots, caches |
| Piper  | Pine Script v6 generation, lint, export (`tradingview/*.pine`) |
| Quinn  | TradingView-semantics bar emulator, walk-forward, sweeps, Monte-Carlo |
| Mira   | `DeskMemory` — Hebbian `preset × symbol@timeframe` synapses, lessons, episodes |
| Sol    | `FlyConnectome` — fly-brain sensorimotor mapping to **human-gated** motor proposals |

Module: `aoa.tradingview`. CLI: `aoa tradingview` (`tv`). Memory:
`data/tradingview/memory.json`. Webhook: `POST /api/tradingview/webhook`.

## Why

TradingView is where the human runs strategies. The desk gives every preset a
Python twin backtested with TradingView's own fill model (next-bar-open fills,
intrabar stop/target path, percent-of-equity sizing, commission + slippage),
validated out-of-sample by walk-forward, across HFT → position horizons on
crypto and ~2000 US stocks across NASDAQ / NYSE / NYSE American / Arca / Cboe /
IEX. Learned trust persists between runs; the connectome turns the same
evidence into a proposal shape the human can approve or reject.

## Constraints kept

- Hard Safety Floor untouched: the desk never imports a broker; approving a
  webhook proposal only records the decision.
- ATTL auto-12, Kai critical-only, Aaron's twelve unchanged.
- Fundamentals snapshots are *current*, not point-in-time — the desk treats
  them as a universe filter, never a timing signal, and says so in reports.
- HFT (seconds) presets have no free public seconds data; they are validated
  on the synthetic microstructure generator and by TradingView's own tester
  with Bar Magnifier. Reports flag `source=synthetic` when this is the case.

## CLI

```bash
python3 -m aoa.cli tv presets
python3 -m aoa.cli tv pine --all                      # → tradingview/*.pine
python3 -m aoa.cli tv backtest swing-equity-1d-trend --symbol AAPL --folds 3 --monte-carlo
python3 -m aoa.cli tv desk run --symbols AAPL,BTC-USD --folds 3
python3 -m aoa.cli tv universe-sweep --preset swing-equity-1d-trend --limit 200 --workers 4
python3 -m aoa.cli tv memory
python3 -m aoa.cli tv connectome status
```
