# TradingView desk — Pine v6 presets, backtests, memory, connectome

The TradingView desk (`aoa.tradingview`, CLI `aoa tradingview` / `aoa tv`) is
Julie's sub-team for strategies **you** run in TradingView. It ships:

- **17 presets** across horizons — HFT (1s / 5s / 15s), scalp (1m / 5m),
  intraday (15m), swing (1h / 4h / 1D), position (1D / 1W) — for crypto and
  US equities, each with an ATR risk model, a cost model, and a walk-forward
  parameter grid.
- A **Pine Script v6 generator** so every preset is one paste away from a
  TradingView chart, with JSON alerts wired to the AOA webhook.
- A **backtester that mimics TradingView's strategy tester** (fill rules,
  sizing, costs) so the offline numbers and the chart's Strategy Tester agree.
- **Walk-forward** validation, parameter sweeps and Monte-Carlo trade
  shuffles across timeframes.
- Public, keyless **data**: Yahoo (10y daily · 2y hourly · 60d 5/15/30m · 7d
  1m), Coinbase and Kraken (crypto), the Nasdaq Trader symbol directories for a
  ~2000-stock US universe across NASDAQ / NYSE / NYSE American / Arca / Cboe /
  IEX, and Yahoo fundamentals snapshots.
- **Neural memory** (`DeskMemory`): Hebbian synapses `preset × symbol@timeframe`
  learned from out-of-sample results, persisted in `data/tradingview/memory.json`.
- A **fly-brain connectome** (`FlyConnectome`) that maps the same evidence to a
  motor proposal — always `requires_human=True`.

Nothing in this package imports a broker. It never places orders.

## Quick start

```bash
pip install -e ".[dev,web]"

aoa tv presets                                   # catalogue
aoa tv pine swing-equity-1d-trend                # Pine v6 to stdout
aoa tv pine --all                                # tradingview/*.pine

# one preset, one symbol, real data, walk-forward + Monte-Carlo
aoa tv backtest swing-equity-1d-trend --symbol AAPL --folds 3 --monte-carlo --trades

# the desk cycle: Dara fetch → Quinn backtest → Mira learn → Sol propose → report
aoa tv desk run --symbols AAPL,MSFT,BTC-USD --folds 3 --workers 4 --export-pine
aoa tv desk status
aoa tv memory
aoa tv connectome status
```

Offline / CI: add `--source synthetic --seed 1` — a seeded regime-switching
generator stands in for the network.

## Presets

| Preset | Horizon | Market | TF | Family | Shorts |
|--------|---------|--------|----|--------|--------|
| `hft-crypto-1s-momentum` | hft | crypto | 1s | EMA(5/13)+RSI(7)+VWAP | yes |
| `hft-crypto-5s-orderflow` | hft | crypto | 5s | bar-delta z-score | yes |
| `hft-crypto-15s-meanrev` | hft | crypto | 15s | Bollinger fade | yes |
| `scalp-crypto-1m-momentum` | scalp | crypto | 1m | EMA(8/21)+RSI(9)+VWAP+volume | yes |
| `scalp-equity-1m-momentum` | scalp | equity | 1m | EMA(9/21)+RSI(9)+VWAP, session-bound | no |
| `scalp-equity-5m-orderflow` | scalp | equity | 5m | bar-delta z-score, session-bound | no |
| `intraday-equity-15m-breakout` | intraday | equity | 15m | Donchian(20) + volume, trailing | no |
| `intraday-crypto-15m-supertrend` | intraday | crypto | 15m | Supertrend(10,3) + MACD | yes |
| `swing-equity-1h-supertrend` | swing | equity | 1h | Supertrend + MACD | no |
| `swing-equity-4h-breakout` | swing | equity | 4h | Donchian(30), trailing | no |
| `swing-equity-1d-trend` | swing | equity | 1D | Supertrend + MACD | no |
| `swing-equity-1d-breakout` | swing | equity | 1D | Donchian(55) + volume, trailing | no |
| `swing-crypto-4h-momentum` | swing | crypto | 4h | EMA(21/55)+RSI(14) | yes |
| `swing-crypto-1d-meanrev` | swing | crypto | 1D | Bollinger fade + RSI | no |
| `position-crypto-1d-trend` | position | crypto | 1D | Supertrend + MACD | yes |
| `position-equity-1d-fundamental` | position | equity | 1D | 12-1 momentum > SMA200, fundamentals gate | no |
| `position-equity-1w-fundamental` | position | equity | 1W | 52w momentum > SMA40, fundamentals gate | no |

Equity presets are long-only (cash account), session-bound where intraday
(`0935-1555`, flat into the close, per-day trade caps). Override the timeframe
with `--timeframe` on any command to test the same rules on another horizon.

## Putting a preset on a TradingView chart

1. `aoa tv pine <preset> --out my.pine` (or `--all`).
2. TradingView → Pine Editor → paste → **Add to chart**. Pick the chart
   timeframe named in the script header. Seconds charts need a Premium+ plan;
   keep **Bar Magnifier** on for honest intrabar fills.
3. Strategy Tester → Properties: the script already sets
   `process_orders_on_close=false`, percent-of-equity sizing, percent
   commission and tick slippage to match the offline emulator.
4. Alerts: create an alert on the strategy, condition *Order fills only*,
   message `{{strategy.order.alert_message}}`, webhook URL
   `https://<your-host>/api/tradingview/webhook`. Set
   `AOA_TRADINGVIEW_WEBHOOK_SECRET` and add `"token": "<secret>"` to the alert
   payload (or send `X-AOA-Token`).

Every alert lands in the human-gated queue:

```bash
curl -s localhost:8000/api/tradingview/alerts?status=pending
curl -s -X POST localhost:8000/api/tradingview/alerts/<id>/respond \
     -H 'content-type: application/json' -d '{"action":"approve","note":"ok"}'
```

Approving **records a decision**; it does not trade. Execution remains with the
existing risk-guarded broker path and `AOA_LIVE_ACK`.

## How the emulator matches TradingView

| TradingView | Emulator |
|-------------|----------|
| orders placed on bar close fill at next bar open | `EmulatorConfig(fill_on_close=False)` (default) |
| `process_orders_on_close=true` | `fill_on_close=True` |
| stop/limit exits evaluated intrabar, path open→nearer extreme→farther→close | `_intrabar_hits`; both touched → nearer extreme wins; `conservative_intrabar=True` always takes the stop |
| stop gapped through → fills at open | `_gap_fill` |
| `strategy.percent_of_equity` | `RiskModel.qty_pct_equity`; equities round down to whole shares |
| `commission_type=percent` | `CostModel.commission_pct` per side |
| `slippage=<ticks>` | `slippage_ticks × tick_size` (or `slippage_pct` when tick unknown) |
| trailing stop ratchets on close | same (`trail_atr`) |
| `strategy.close(..., immediately=true)` at session end | `session_end` exits at the bar close |

Metrics: net/gross profit, profit factor, win rate, expectancy, SQN, Sharpe,
Sortino, max drawdown, CAGR, buy-and-hold, exposure, trades per year, exit
reasons. Research: `sweep` (grid), `walk_forward` (rolling or anchored, strict
OOS), `monte_carlo_trades` (shuffle realised trades → drawdown percentiles).

## Data, universe, fundamentals

```bash
aoa tv universe --n 2000 --csv universe.csv        # Nasdaq Trader directories, common stock only
aoa tv universe-sweep --preset swing-equity-1d-trend --offset 0 --limit 250 --workers 4
aoa tv fundamentals NVDA --preset position-equity-1d-fundamental
```

- Candles are cached under `data/tradingview/cache/<source>/` and merged on
  every refresh, so history keeps growing between runs.
- `source=auto`: equities → Yahoo; crypto → Yahoo for daily+ (10y), otherwise
  Coinbase (pages back ~3000 candles) → Kraken (latest 720) → Yahoo. Missing
  intervals (4h) are resampled from the finest native one; intraday equity
  bars anchor to the 09:30 ET open like TradingView.
- Fundamentals are a *current snapshot*, not point-in-time. The desk applies
  them as a universe filter and marks the row `fundamentals gate: …`; grade
  position presets on the walk-forward OOS numbers.
- HFT presets: no free seconds-bar feed exists. They are validated on the
  synthetic microstructure generator here (`source=synthetic` in reports) and
  on TradingView's own tester with Bar Magnifier.

### Why the 1s/5s presets often show `trades=0`

HFT and scalp presets carry `min_edge_cost_mult` (2.0 for HFT, 1.5 for
scalp). Before every entry the emulator — and the generated Pine
(`minEdgeMult`) — checks that the ATR-scaled target clears that multiple of
the **round-trip** cost (commission both sides + slippage both sides). On 1s
BTC bars the target is a few basis points while a taker fee schedule
(0.04 % + 1 tick per side) costs ~10 bp round trip, so the gate refuses every
signal. The report says so instead of pretending:

```
+0.000  hft-crypto-1s-momentum  BTC-USD  1S  trades=0 ... cost-gated=50 (edge/cost≈0.36, need 2.00)
note: 4 row(s) took no trades because the ATR edge never cleared fees ...
```

`entries_blocked_by_edge`, `median_edge_cost_ratio` and
`required_edge_cost_ratio` are in the row metrics. To make a seconds preset
tradeable you must change the *economics*, not the gate: model a maker /
rebate fee (`--param` is not enough — edit `CostModel` on the preset and set
`commission_value` in the Pine header to match), widen `target_atr`, or move
to the 15s / 1m presets which do clear costs on volatile pairs. Turning the
gate off (`min_edge_cost_mult=0`) reproduces the classic "100 % losing scalper"
result that fees guarantee.

## Neural memory

`DeskMemory` (`data/tradingview/memory.json`, override with
`AOA_TRADINGVIEW_MEMORY_PATH`):

- **synapse** per `preset|SYMBOL|tf`: `weight ← weight + η (reward − weight)`,
  reward ∈ [−1, 1] from OOS SQN, profit factor and drawdown (≥3 trades needed),
  decayed by 3% per consolidation; stale near-zero synapses are pruned.
- **aggregates**: preset / symbol / timeframe trust; **lessons** distilled for
  LLM members (`to_prompt_block()`); **episodes**; **agents** seen; the
  connectome's weights.

`aoa tv memory` prints trust and lessons; `aoa tv memory --json` is machine
readable. Nova sees each desk run as a `brain/captures/` note.

## Fly connectome → motor output

| Fly circuit | Desk role |
|-------------|-----------|
| optic / antennal lobes | `MarketSense`: trend, momentum, order-flow, volatility, drawdown, memory trust, exposure, fundamentals |
| Kenyon cells | sparse k-winners code of the sense vector (seeded random projection) |
| MBONs + DANs | valence weights per KC; `reinforce(reward)` = dopamine (eligibility × reward) |
| APL | global inhibition from volatility + drawdown (risk-off gain) |
| central complex | goal exposure vs actual exposure → steering error |
| descending neurons | `enter_long · enter_short · hold · reduce · exit`, winner-take-all |
| motor neurons | `MotorCommand` — a **proposal**, `requires_human=True` |
| ascending neurons | fills / PnL → `reinforce` |

Probe it: `aoa tv connectome step --trend 0.8 --momentum 0.6 --exposure 0.5`.

## Safety (Hard Floor)

- `aoa.tradingview` never imports `aoa.brokerage` or the executor.
- Reports carry `never_live: true`; webhook approve/reject only records.
- Deterministic cash guards in `src/aoa/risk/guards.py` stay binding for the
  live swarm path; nothing here bypasses `AOA_LIVE_ACK`.
- Do not put exchange credentials in Pine alert payloads or in `data/`.
