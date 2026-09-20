# Design: TradingView desk (Pine v6 presets · TV-semantics backtests · neural memory · fly connectome)

> **Status:** Active — sub-team outside the ATTL twelve, human has final say
> **Owner:** Julie (algorithms) · risk sign-off Andrea · critical-only review Kai
> **Module:** `aoa.tradingview` · **CLI:** `aoa tradingview` (`tv`) · **Docs:** [how-to](../how-to/tradingview-desk.md)
> **Decision:** [brain/decisions/2026-09-20-tradingview-desk-outside-twelve.md](../../brain/decisions/2026-09-20-tradingview-desk-outside-twelve.md)

## Problem

The human runs strategies in TradingView. Anything we hand over must (a) be a
real Pine v6 `strategy()` that compiles and alerts, (b) have been backtested
with **TradingView's own fill semantics** so the chart's Strategy Tester and our
numbers agree, (c) hold up **out-of-sample** across timeframes and a wide
universe (crypto + ~2000 US stocks on several exchanges), (d) combine
technical and fundamental filters, and (e) leave every execution decision with
the human. Learned trust must persist so the desk gets smarter between runs.

## Locked decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Where rules live | **One preset → two twins**: Python (`rules.py`) and Pine (`pine.py`) generated from the same `Preset` |
| 2 | Fill model | Mirror TradingView: next-bar-open fills, intrabar stop/target path, gap fills, percent-of-equity, percent commission, tick slippage |
| 3 | Validation | Walk-forward (rolling/anchored) with strict OOS; reward memory from OOS metrics (70%) + in-sample (30%) |
| 4 | Data | Keyless public providers with growing CSV cache; seeded synthetic fallback so CI/offline always works |
| 5 | Fundamentals | Universe filter, not timing signal (snapshot ≠ point-in-time); Pine uses `request.financial()` |
| 6 | Team shape | 5 deterministic members (Dara, Piper, Quinn, Mira, Sol) **outside** the twelve, led by Julie |
| 7 | Memory | Hebbian synapses `preset × symbol@tf` + lessons + connectome weights in one JSON |
| 8 | Motor mapping | Fly connectome wiring diagram; output is a `MotorCommand` proposal, `requires_human=True` |
| 9 | Execution | **Never.** No broker imports; webhook approve records only |

## Architecture

```
                 ┌──────────── Preset (presets.py) ────────────┐
                 │ family · params · RiskModel · CostModel      │
                 │ FundamentalFilter · tunable grid · timeframe │
                 └──────┬───────────────────────────┬───────────┘
          build_strategy│                           │generate_pine
                        ▼                           ▼
             rules.py (Python twin)        tradingview/<preset>.pine
      EMA/RMA/RSI/ATR/Stdev/Supertrend/     strategy() · inputs · session ·
      session VWAP · Signal per bar         request.financial gate · ATR exits ·
                        │                   JSON alert_message
                        ▼                                   │
   data.py ──bars──▶ backtest.py (emulator) ◀── EmulatorConfig   │ alert webhook
   yahoo/kraken/     next-open fills · intrabar path ·           ▼
   coinbase/synthetic gap fill · % equity · costs        webhook.py → alerts.jsonl
   + CSV cache        metrics · sweep · walk_forward ·   (pending → approve/reject,
   universe.py        monte_carlo_trades                 executed=False always)
   fundamentals.py           │
                             ▼
                     memory.py DeskMemory ──── connectome.py FlyConnectome
                     synapses · trust · lessons  KC → MBON/DAN → APL → CX → DN → MotorCommand
                             ▲                                      │
                             └──────────── desk.py DeskRunner ───────┘
                       Dara fetch → Quinn backtest → Mira learn → Sol propose → report
                                     └─▶ data/tradingview/reports · brain/captures
```

## Data flow of one desk cycle

1. **Dara** resolves `(symbol, timeframe)` → provider order (`auto`), merges the
   CSV cache, fetches fundamentals when the preset gate is enabled.
2. **Quinn** runs `run_backtest` (full history, warm-up excluded from metrics),
   `walk_forward` (folds; parameters chosen on IS only; OOS warmed on IS bars
   but no entry before the boundary counts), `monte_carlo_trades`.
3. **Mira** squashes metrics to `reward ∈ [-1, 1]` (`tanh(SQN/2.5)`,
   `tanh(log PF)`, drawdown penalty, evidence = min(1, n/30)), blends
   0.7·OOS + 0.3·IS, clamps to ≤ 0 when the fundamentals gate failed, updates
   the synapse, decays all, distils lessons, appends an episode.
4. **Sol** builds `MarketSense` from the last bar's features + memory trust,
   steps the connectome, reinforces with the row's reward, records a proposal.
5. **Piper** (optional) regenerates and lints Pine for the presets used.
6. Report JSON → `data/tradingview/reports/`, summary → `brain/captures/`.

## Emulator edge cases

| Case | Behaviour |
|------|-----------|
| stop and target both inside one bar | distance from open decides which extreme is hit first; `conservative_intrabar` forces the stop |
| stop gapped through at the open | fills at the open (worse than the level) |
| trailing + fixed stop | max(fixed, trail) for longs / min for shorts, ratchet on close only |
| last in-session bar | `session_end` exit at the close; no new entries |
| per-day cap | counted per session date at fill time |
| equities | whole shares; `fractional_equity=True` to relax |
| open trade at series end | force-closed at last close, reason `end` |
| too few trades for an objective | `objective_value → -inf` so sweeps never pick a 2-trade fluke |
| OOS/IS ratio | only computed when the IS objective is positive |

## Timeframe coverage vs data availability

| TF | Equity source | Crypto source | Note |
|----|---------------|---------------|------|
| 1s / 5s / 15s | — | — | synthetic only; validate on TradingView with Bar Magnifier |
| 1m | Yahoo 7d | Coinbase ~2d (3000 bars) | thin — cache grows each run |
| 5m / 15m / 30m | Yahoo 60d | Coinbase pages back | |
| 1h | Yahoo 730d | Coinbase pages back | |
| 4h | Yahoo 1h resampled (09:30-anchored) | Coinbase 1h resampled (epoch) / Kraken | |
| 1D | Yahoo 10y | Yahoo 10y → Coinbase → Kraken | deepest; the universe sweep runs here |
| 1W | Yahoo 20y | Kraken | |

## Memory & connectome

- Synapse update: `w ← w + η (r − w)`, η = 0.3; decay 0.97 per consolidation;
  prune |w| < 1e-3 after > 5 samples. Aggregates = mean weight by preset /
  symbol / timeframe. Lessons are regenerated from aggregates each run.
- Connectome: 64 KCs, k = 8 active, seeded Gaussian projection (reproducible
  wiring); valence = tanh(Σ w_active / √k); DAN rule
  `w_i ← clip(w_i + lr · r · e_i, ±3)` with eligibility decay 0.6; APL
  inhibition = clip(0.6·vol + 0.8·dd); goal heading = tanh(1.5·evidence +
  0.8·valence + 0.5·trust), quartered for longs when fundamentals fail; DN
  drives with entry channels damped while any position is open (reversal exits
  first); winner-take-all with margin confidence.

## Testing

`tests/test_tradingview_*.py` (113 tests) — indicator equivalence vs
`aoa.data.indicators`, scripted-fill semantics, metrics, sweep/walk-forward fold
integrity (incl. fundamentals gate), Monte-Carlo, memory learning/decay/
persistence, connectome determinism/reinforcement/inhibition/human gate, every
preset's Pine lint + surfaced inputs, desk end-to-end on synthetic data,
webhook validation/token/respond, web routes, CLI commands.

## Non-goals

- Live or paper order routing from this package.
- Tick-level LOB simulation (see `aoa.hftbacktest`, `aoa.visualhft`).
- Point-in-time fundamentals (would need a paid vendor).
