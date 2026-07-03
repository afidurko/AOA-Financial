# AOA Financial — Autonomous Agentic Trading Swarm

An autonomous, multi-agent swarm that analyzes the US stock market for
opportunities and executes **stock and options** trades in a **cash account**
through a live brokerage. The brokerage ([Alpaca](https://alpaca.markets)) is
both the **information source** (quotes, bars, option chains, account, positions)
and the **order executor**. Every agent reasons with **Claude** (`claude-opus-4-8`).

> ⚠️ **This software can place real orders with real money.** It defaults to
> **paper trading** (`ALPACA_LIVE=false`). Set `ALPACA_LIVE=true` only when you
> intentionally route orders to a live account. Hard, deterministic risk
> guardrails always apply, but **you are responsible for any trades it makes.**
> Start in the paper sandbox. Nothing here is financial advice.

---

## Repository overview

This repo contains **two complementary packages** that can be used independently:

| Package | Role | Entry point |
|---------|------|-------------|
| **`src/aoa/`** | Live **autonomous trading swarm** — Alpaca brokerage, options, cash-account guardrails, web dashboard | `aoa` |
| **`aoa_financial/`** | Optional **deep analysis & forecasting engine** — SQLite history (back to 1960), factor/regime models, walk-forward backtest. **Does not place orders.** | `python -m aoa_financial` |

The sections below document the trading swarm (`src/aoa/`). For the optional research engine, see [Optional: Deep analysis engine (`aoa_financial/`)](#optional-deep-analysis-engine-aoa_financial).


---

## How it works

Each **cycle** runs a **composable pipeline** of stages over a shared blackboard
and editable swarm environment:

```
 intake → scan → analyze → portfolio → materialize → risk → execute
   │        │        │          │                         │
   └────────┴────────┴──────────┴── SwarmEnvironment ────┘
              (global / domain / meshed edits + checkpoints)
```

Stages emit events on the blackboard event bus and snapshot the environment at
**checkpoints** (after scan, analyze, portfolio, risk) so you can edit mid-cycle
via `orchestrator.run_until("portfolio")` before downstream stages run.

Per-symbol analysis runs **in parallel** when `AOA_PARALLEL_WORKERS > 1`
(technical + fundamental concurrently per symbol, symbols analyzed concurrently).

```
 broker (Alpaca)
   │  account, positions, quotes, multi-TF bars, news, option chains
   ▼
┌──────────────┐   shortlist    ┌──────────────┐   signals    ┌────────────────┐
│   Scanner    │ ─────────────▶ │  Technical   │ ───────────▶ │   Meshing    │
│ (universe →  │                │  Fundamental │              │  (unified    │
│  candidates) │                │              │              │   per-symbol │
└──────────────┘                └──────────────┘              │   view)      │
                                                              └───────┬────────┘
                                                                      │
                                                              ┌───────▼────────┐
                                                              │   Portfolio    │
                                                              │    Manager     │
                                                              │ (synthesize →  │
                                                              │  target trades)│
                                                              └───────┬────────┘
                                                                      │ proposals
                                                                      ▼
                                          ┌───────────────────────────────────┐
                                          │  Risk Manager                     │
                                          │  • deterministic cash-account     │
                                          │    guardrails (binding)           │
                                          │  • LLM holistic veto (can only    │
                                          │    tighten, never loosen)         │
                                          └───────────────┬───────────────────┘
                                                          │ approved
                                                          ▼
                                                    ┌───────────┐
                                                    │ Executor  │ ──▶ broker
                                                    └───────────┘     (or dry-run)
```

Every step is written to an append-only JSONL **journal** for a full audit trail.

### The agents

The swarm is coordinated by a **five-member agent team** before trades are proposed:

| Member | Role |
|--------|------|
| **Tom** | Trend analyst — reads price action and characterizes prevailing trends. |
| **Julie** | Algorithm specialist — validates and refines Tom's reads with quantitative methods. |
| **Bob** | Systems health — checks config, broker connectivity, and code integrity (deterministic). |
| **Alan** | Decision aggregator — synthesizes Tom and Julie into a focused decision brief. |
| **Aaron** | CEO — fixes team issues when possible; pushes iPhone alerts (never email) when he can't fix or needs your verification. |

Behind them, specialized trading agents still handle scanning, fundamentals, options,
portfolio sizing, risk, and execution:

| Agent | Role |
|-------|------|
| **Scanner** | Narrows the universe to a shortlist of the strongest setups. |
| **Technical** | Multi-timeframe indicators (1m→yearly: SMA/EMA/RSI/MACD/Bollinger/ATR/vol) → signal. |
| **Fundamental** | Alpaca news headlines + catalyst/event-risk view (never fabricates news). |
| **Meshing** | Synthesizes specialist signals into a cohesive, editable per-symbol view. |
| **Options strategist** | Proposes a cash-account-appropriate options structure from the live chain. |
| **Portfolio manager** | Synthesizes all signals + team brief + positions + account into target trades. |
| **Risk manager** | Enforces hard guardrails, then an LLM second-opinion veto. |

### Cash-account safety invariants (always enforced, deterministically)

- **No equity shorting** — a sell is only allowed to close an existing long.
- **No naked short options** — only covered calls / cash-secured puts.
- **Per-position cap** (`AOA_MAX_POSITION_PCT`) — counts your **existing** holding
  in that name (equity + options on the same underlying) plus anything already
  approved this cycle, so a name can't be accumulated past the cap across cycles.
- **Options-book cap** (`AOA_MAX_OPTIONS_PCT`).
- **Minimum settled-cash buffer** (`AOA_MIN_CASH_BUFFER_PCT`), measured against
  **effective settled cash** (broker cash minus locally-tracked unsettled sale
  proceeds — see below).
- **Daily-loss kill switch** (`AOA_MAX_DAILY_LOSS_PCT`) — halts new risk, still allows exits.
- **Per-cycle order cap** (`AOA_MAX_ORDERS_PER_CYCLE`).

These are pure functions of the proposal/account/limits — no LLM in the loop — so
they cannot be "talked around" by a model.

### Settlement & persistent state

State that must survive process restarts lives in a small JSON file
(`AOA_STATE_PATH`, default `journal/state.json`):

- **Daily-loss baseline.** The equity the day started at is persisted, so an
  intraday restart can't silently disarm the kill switch by resetting the
  baseline.
- **Settlement ledger (good-faith-violation avoidance).** Cash accounts settle
  T+1. When the swarm sells, the proceeds are recorded as *unsettled* until the
  next business day and subtracted from the cash the swarm treats as available —
  so it won't redeploy unsettled proceeds and trip a good-faith violation.

### Protective exits & re-entry guard

- **Every equity entry ships with a protective stop.** New long entries are
  submitted as a broker **bracket/OTO** order carrying a stop-loss (and a
  take-profit) so the stop persists between cycles. The stop is the technical
  agent's suggested level, falling back to a 1.5×ATR stop, then a fixed 8% stop —
  there is always one. (Long options are inherently defined-risk, so they don't
  carry a separate stop.)
- **Re-entry guard.** The swarm never opens a new position in a name it already
  holds or already has a working (unfilled) order on — preventing duplicate and
  stacked orders. Exits are always still allowed.

---

## Market-trend analysis & scenario simulation

Alongside the live trading swarm, the `aoa.simulation` package analyzes **past**
market behavior and recreates plausible **future** scenarios — entirely offline,
with **no LLM and no orders**. It's pure-Python (no numpy/pandas) and fully
seedable, so every result is reproducible.

**1. Trend analysis** (`aoa.simulation.trends`) — characterizes a bar history:
trend direction & strength (regression slope + R²), CAGR, the full daily-return
distribution (vol, skew, fat-tailedness), a labeled regime (`bull` / `bear` /
`choppy_volatile` / `sideways` …), and every drawdown deeper than a threshold
(depth, duration, whether it recovered).

**2. Scenario library** (`aoa.simulation.scenarios` + `aoa.simulation.historical`)
— two kinds of named stress scenarios:

- **Stylized** (`[synth]`) — reproducible, *seeded* recreations of well-known
  episodes (1987, 2008, the 2020 COVID crash, the 2022 rate shock, melt-ups,
  V-recoveries, …), each calibrated to its headline drawdown/duration/vol.
- **Real historical tapes** (`[real]`) — the *actual* daily-return sequences of a
  major index across famous windows (1929, 1987, Oct-2008, Feb–Mar-2020), taken
  from public closes. These reproduce history's exact path, gap-downs and all.

You can also **extract** a scenario from any window of live bars to replay it
against a current position.

**3. Monte-Carlo simulator** (`aoa.simulation.simulator`) — fits a return process
to history and projects many forward paths:

- **GBM** — geometric Brownian motion from the estimated drift/vol (smooth, parametric).
- **Block bootstrap** — resamples contiguous blocks of real returns, preserving
  fat tails and short-run autocorrelation.
- **Scenario replay / stress test** — deterministically applies any scenario to
  the current price.

The simulator summarizes the outcome distribution: expected return, P(profit),
ending-price percentiles (p5…p95), and **95% VaR / CVaR**.

**4. Live, adaptive tracking** (`aoa.simulation.live`) — the analysis above is
static; `LiveMarketTracker` makes it **dynamic**. It polls the broker for fresh
quotes and bars, and on every refresh it:

- anchors the projection to the **live quote mid** (not the last completed bar);
- re-fits the model with **recency-weighted (EWMA) drift/vol** — older returns
  decay by ½ every `halflife` bars, so it tracks the *current* regime instead of
  averaging stale history;
- diffs against the previous refresh to flag **regime shifts**, large spot moves,
  fresh drawdowns, and volatility spikes;
- writes each update to the JSONL journal for the same audit trail the swarm keeps.

It depends only on the abstract `Broker`, so it adapts to live Alpaca, the paper
sandbox, or a test broker identically.

```python
from aoa.simulation import analyze_trends, MarketSimulator, SimulationConfig, list_scenarios
from aoa.simulation import LiveMarketTracker

bars = broker.get_bars("AAPL", "1Day", 252)
print(analyze_trends(bars, "AAPL").to_dict())

sim = MarketSimulator(seed=1)
result = sim.simulate(bars, SimulationConfig(method="gbm", horizon=21, n_paths=5000), symbol="AAPL")
print(result.summary())
for s in sim.stress_test(result.start_price, list_scenarios()):
    print(s.scenario, s.total_return_pct, s.max_drawdown_pct)

# Live, adaptive: re-analyze + re-simulate as the market moves.
tracker = LiveMarketTracker(broker, ewma_halflife=63)
tracker.stream(["AAPL", "MSFT"], interval=30,
               on_update=lambda u: print(u.summary()),
               market_gate=broker.is_market_open)
```

---

## Optional: Deep analysis engine (`aoa_financial/`)

A deep stock-market **analysis, forecasting, and decision engine**. It builds
its own databases of market history (back to **June 1960**), runs a quant stack
of technical / fundamental / forecasting / regime / factor models,
**reverse-engineers the latent drivers** behind a stock's trend, layers a
**Claude Opus 4.8** analyst on top, and fuses everything through a **multi-agent
"swarm"** into a sized BUY / HOLD / SELL decision.

> **Design principle:** the entire core runs on the **Python standard library
> alone** — no numpy, pandas, or network required. `anthropic`, `numpy`, and
> live data feeds are *optional accelerators* that are detected at runtime and
> used when present, with graceful fallback otherwise. This makes the system
> reproducible and runnable anywhere.
>
> **numpy acceleration:** when numpy is installed, the analysis core
> automatically routes its hot numeric paths — log/simple returns, standard
> deviation, SMA/EMA, OLS (SVD `lstsq`), the rolling **factor panel**, and the
> **Monte-Carlo** forecast — through a vectorised backend (`analysis/_backend.py`).
> On a full 1960-to-date series this is ~**4× faster** while running more
> simulation paths, and the results match the pure-Python path to machine
> precision (locked by parity tests). `pip install numpy` to enable; nothing
> else changes.
>
> **pandas DataFrame layer:** an optional tabular front-end
> (`analysis/frames.py`) provides DataFrame/CSV IO with the SQLite store, a
> one-pass **vectorised indicator suite** (SMA/EMA/RSI/MACD/Bollinger/ATR/
> returns/vol/drawdown as columns), a wide cross-ticker close-price panel, and
> a return-correlation matrix. Its indicators are held in **parity** with the
> scalar `analysis/technical.py` by the test-suite. It is imported only on
> demand — the stdlib core never depends on it. `pip install pandas` enables
> the `frame` and `corr` commands and `ingest_dataframe()`.

---

## Quick start

```bash
# No install needed — pure stdlib. (Optional: pip install -r requirements.txt)

# 1. Build the DB and ingest the default universe (synthetic history to 1960)
python -m aoa_financial init

# 2. Deep analysis + swarm decision for one name
python -m aoa_financial analyze AAPL

# 3. Reverse-engineer the forces driving a trend
python -m aoa_financial reverse XOM

# 4. Probabilistic forecast
python -m aoa_financial forecast MSFT --horizon 21

# 5. Rank decisions across many names
python -m aoa_financial swarm AAPL MSFT XOM JPM KO

# 6. Vectorised indicator panel (pandas) — print tail or export CSV
python -m aoa_financial frame AAPL --tail 10
python -m aoa_financial frame AAPL --csv aapl_indicators.csv

# 7. Cross-sectional return-correlation matrix (pandas)
python -m aoa_financial corr AAPL MSFT XOM JPM KO --window 252

# 8. Fetch & score real fundamentals (live provider if a key is set)
python -m aoa_financial fundamentals AAPL
python -m aoa_financial fundamentals AAPL --provider fmp --refresh

# 9. Walk-forward backtest of the swarm's decisions (no lookahead)
python -m aoa_financial backtest AAPL XOM JPM KO --horizon 21 --step 63

# Or the full guided demo:
python examples/run_demo.py
```

Add `--live` to prefer real history from Stooq before falling back to the
synthetic generator. Add `--json` to any command for machine-readable output.

---

## Architecture

```
                ┌─────────────────────────────────────────────────────────┐
                │                    swarm/  (decision)                    │
                │   technical · fundamental · forecast · regime ·          │
                │   sentiment · LLM   →  weighted-confidence vote  →       │
                │              BUY / HOLD / SELL  + position size          │
                └───────────────▲─────────────────────────▲───────────────┘
                                │                         │
                ┌───────────────┴───────────┐   ┌─────────┴───────────────┐
                │        analysis/           │   │          llm/           │
                │  technical · fundamentals  │   │   ClaudeAnalyst         │
                │  forecast · regimes ·      │──▶│   (Opus 4.8, adaptive   │
                │  factors · sentiment ·     │   │   thinking + structured │
                │  reverse_engineer          │   │   output) ⇄ offline     │
                └───────────────▲────────────┘   └─────────────────────────┘
                                │
                ┌───────────────┴────────────┐   ┌─────────────────────────┐
                │        ingest/             │   │      databases/         │
                │  synthetic (to 1960) ·     │──▶│  SQLite: prices,        │
                │  loaders (Stooq, live)     │   │  fundamentals,          │
                └────────────────────────────┘   │  sentiment, regimes,    │
                                                 │  signals, decisions     │
                                                 └─────────────────────────┘
```

### Layers

| Layer | Module | What it does |
|-------|--------|--------------|
| **Databases** | `databases/` | SQLite store (`schema.sql`) with typed DAL for prices, fundamentals, sentiment, inferred regimes, per-agent signals and final decisions. |
| **Ingest** | `ingest/` | `SyntheticGenerator` — deterministic regime-switching GBM producing full OHLCV history back to **1960‑06‑01** for *any* ticker. `loaders` add an optional Stooq CSV feed with automatic offline fallback. |
| **Analysis** | `analysis/` | Technical indicators (SMA/EMA/RSI/MACD/Bollinger/ATR/vol/drawdown), fundamental scoring, an **ensemble forecaster** (Monte-Carlo + trend regression + EWMA), **regime inference** (bull/recovery/sideways/correction/bear), a **linear factor model** (momentum/reversal/trend/volatility/market), lexicon sentiment, and the **reverse-engineering** synthesis. |
| **LLM** | `llm/` | `ClaudeAnalyst` turns the quant evidence into a structured investment view via **Claude Opus 4.8**. Falls back to a deterministic offline analyst when no API key / SDK. |
| **Swarm** | `swarm/` | Independent specialist agents each emit a directional signal; the swarm aggregates by **weight × confidence**, penalises disagreement, and sizes a portfolio weight. |

---

## Reverse-engineering market trends

`analysis/reverse_engineer.py` is the synthesis the brief asks for. Given a
price history it:

1. **Fits a factor model** of next-day returns on engineered factors
   (momentum, short-term reversal, trend, volatility, optional market beta) and
   reads off the dominant drivers and explained variance (R²).
2. **Decomposes** realised performance into a *trend (drift)* component and a
   *risk (volatility)* component, yielding a Sharpe-like `trend/risk` read.
3. **Infers the current regime** and blends a robust **sentiment** reading.
4. Synthesises a single forward-looking **bias score** in `[-1, 1]`.
5. Emits explicit **inferences** (what the data implies) and **assumptions**
   (what must hold for the read to be valid) — so every conclusion is auditable.

```bash
python -m aoa_financial reverse AAPL
```

---

## The Claude analyst

The `llm/` layer sends the *computed quant evidence* (not raw prices) to
**Claude Opus 4.8** and asks for a disciplined investment view returned as
**structured JSON** (thesis, action, conviction, confidence, drivers, risks).
It uses adaptive thinking, high effort, and streaming — see
`llm/analyst.py`. To enable the live analyst:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install anthropic
python -m aoa_financial analyze AAPL          # now uses Claude
```

Without a key it transparently uses a deterministic offline analyst that
reaches the same kind of conclusion from the same dashboard, so the swarm
always gets a meaningful "analyst" vote. Force offline with
`AOA_FORCE_OFFLINE=1`.

---

## Live fundamentals feed

By default fundamentals are synthetic (generated alongside price history). To
pull **real** company fundamentals, set an API key for any supported provider —
the feed (`ingest/fundamentals_feed.py`) auto-selects whichever key is present
and normalises the response to the store's schema (P/E, P/B, dividend yield,
revenue growth, profit margin, debt/equity, ROE, free cash flow):

| Provider | Env var | Endpoint |
|----------|---------|----------|
| Alpha Vantage | `ALPHAVANTAGE_API_KEY` | `OVERVIEW` |
| Financial Modeling Prep | `FMP_API_KEY` | `ratios-ttm` |
| Finnhub | `FINNHUB_API_KEY` | `stock/metric` |

```bash
export FMP_API_KEY=...                       # or ALPHAVANTAGE_API_KEY / FINNHUB_API_KEY
python -m aoa_financial fundamentals AAPL --refresh
python -m aoa_financial analyze AAPL --live-fundamentals      # use live data in the decision
```

Force a provider with `--provider` (or `AOA_FUNDAMENTALS_PROVIDER`). **Every
failure mode is safe:** no key, no network, a rate-limit, or an unknown symbol
transparently falls back to the synthetic generator, so the pipeline never
breaks. All provider parsing is unit-tested with the network mocked — no live
calls are made in the test suite.

## Backtesting (walk-forward, no lookahead)

`backtest/engine.py` replays the swarm's decisions through history to measure
whether the engine has edge. It is strictly **lookahead-free**: at each
rebalance date the decision is built from the bar slice *up to that date only*
(`swarm.decision.evaluate` on `bars[:i+1]`), the entry is that day's close, and
the exit is `bars[i+horizon]`. Holding periods are non-overlapping by default
(`step == horizon`) so the compounded equity curve and Sharpe are well-defined.
Single-latest-value snapshots (stored sentiment, latest fundamentals) are **not**
injected during the backtest, since they would leak the future.

```bash
python -m aoa_financial backtest AAPL XOM JPM KO --horizon 21 --step 63
```

Reported per ticker: number of periods, years covered, **hit rate** (directional
accuracy on actionable signals), **win rate**, strategy vs buy-&-hold **CAGR**,
annualised **excess**, **Sharpe**, and **max drawdown**. The no-lookahead
property is asserted by the test-suite (a decision at index *i* is identical
whether computed from full or future-truncated history).

> On the synthetic data, hit-rate sits near 50% and the tactical strategy
> trails a strongly-trending buy-&-hold — the **expected, honest** result, since
> daily-frequency signals carry little edge. The harness exists so agent weights
> can be tuned against real data on evidence rather than priors.

## The swarm decision engine

Each specialist agent (`swarm/agents.py`) converts one analysis slice into a
signal `(score ∈ [-1,1], confidence ∈ [0,1])`. The aggregator
(`swarm/decision.py`) computes:

* **conviction** = Σ(weight × confidence × score) / Σ(weight × confidence)
* **confidence** = mean agent confidence, shrunk by signal **dispersion**
  (disagreement lowers confidence)
* **target weight** = `|conviction| × confidence`, capped at 15% per name,
  only for BUYs

Agent weights are configurable in `config.py` (`swarm_weights`).

---

## Configuration

All knobs live in `aoa_financial/config.py` and can be overridden with `AOA_`
environment variables, e.g.:

```bash
export AOA_DATA_DIR=/tmp/market
export AOA_LLM_MODEL=claude-opus-4-8
export AOA_LLM_EFFORT=high
```

---

## Tests

```bash
python -m unittest discover -s tests -v     # 17 tests, stdlib only, offline
```

The suite covers the numeric primitives (incl. an OLS sanity check), the
synthetic generator's determinism and length, the store round-trip, every
analysis model, and the full swarm pipeline with persistence.

---

## Data & honesty notes

* **Synthetic history is synthetic.** It has realistic *structure* (regimes,
  macro cycles, fat-tailed shocks) so the models have something genuine to
  discover, but it is **not** real market data and must not be used for actual
  trading. Use `--live` for real Stooq history where available.
* Daily-return factor R² is naturally tiny — daily returns are close to noise.
  The engine reflects this honestly: low explanatory power lowers confidence
  rather than being hidden.
* This is research/educational tooling, **not investment advice**.

---

---

## Install

```bash
git clone <this repo>
cd AOA-Financial
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # or: pip install -r requirements-dev.txt
```

Requires Python 3.10+.

## Configure

Configuration loads in this order (lowest → highest priority):

1. `profiles/{AOA_PROFILE or AOA_ENV}.env` — named environment profile
2. `.env` — your local secrets
3. Shell environment variables — always win

```bash
cp .env.example .env
export AOA_PROFILE=paper-dry    # recommended starting point
# Edit .env: set ANTHROPIC_API_KEY and Alpaca paper keys.
# Leave ALPACA_LIVE=false to use the paper-trading sandbox first.
# Optional market-data tuning:
#   ALPACA_DATA_FEED=iex          # sip | iex | boats | otc (blank = Alpaca default)
#   ALPACA_BAR_ADJUSTMENT=split   # raw | split | dividend | all | spin-off
aoa doctor && aoa run
```

### Named environments

| `AOA_ENV` | Broker | Orders | Use case |
|-----------|--------|--------|----------|
| `test` | n/a | dry-run | Unit tests / CI (no API keys required) |
| `paper-dry` | Alpaca paper | dry-run | Watch decisions without submitting |
| `paper` | Alpaca paper | enabled | Paper trading with real sandbox fills |
| `live` | Alpaca live | enabled | Real money — requires `AOA_LIVE_ACK=I_UNDERSTAND` |

Runtime state (journal, daily-loss baseline) is isolated under `data/{AOA_ENV}/`.

Profiles live in `profiles/` — e.g. `profiles/paper-dry.env`. Override the data
root with `AOA_DATA_DIR` or the journal file with `AOA_JOURNAL_PATH`.

Get free Alpaca **Trading API** paper keys (`PK...`) at <https://alpaca.markets>.
These are **not** the same as Broker API OAuth credentials (`authx.alpaca.markets`).
Options trading requires options approval on the account (the swarm checks `options_level`).

## Run

```bash
aoa doctor            # validate config + check broker/LLM connectivity
aoa doctor --offline  # validate config only (no network)
aoa status            # show account, positions, market clock
aoa run               # run ONE team-coordinated analysis → decision → execution cycle
aoa loop       # run continuously on AOA_CYCLE_SECONDS cadence
aoa team health   # Bob-only systems health check
aoa team brief    # Tom→Julie→Alan analysis without trading
aoa serve      # start the web dashboard + REST API (port 8080)
aoa journal -n 30   # tail the decision/trade journal
aoa report     # activity summary (from journal) + live P&L snapshot

# Market-trend analysis & scenario simulation (no LLM, no orders):
aoa analyze AAPL                       # characterize the historical trend & drawdowns
aoa simulate AAPL --paths 5000 --seed 1   # Monte-Carlo forward paths + scenario stress test
aoa simulate AAPL --method bootstrap   # block-bootstrap (keeps fat tails) instead of GBM
aoa scenarios                          # list the built-in stress-scenario library
aoa watch AAPL MSFT --interval 30      # LIVE: re-analyze & re-simulate as prices move
```

`aoa report` combines journal-derived **activity** (cycles, candidates, orders,
re-entry skips, and the top reasons proposals were risk-blocked) with a live
**P&L snapshot** — open-position unrealized P&L and the day's P&L versus the
persisted baseline. The live half is best-effort and is skipped with a note if
the broker isn't reachable, so the activity summary still works offline.

Set `AOA_DRY_RUN=true` to compute and log decisions **without submitting any
orders** — the recommended way to watch the swarm reason before letting it trade.

### Market data (Alpaca)

All quotes, bars, news, and screeners come from Alpaca using your existing API keys.

| Setting | Default | Purpose |
|---------|---------|---------|
| `AOA_UNIVERSE` | (most-actives) | Tickers to scan, or blank for Alpaca volume leaders |
| `AOA_BAR_TIMEFRAMES` | `1Min,3Min,5Min,15Min,1Hour,1Day,12Month` | Intraday → yearly bar stack |
| `AOA_BAR_FEED` | `iex` | Data feed: `iex` (free tier) or `sip` (all US exchanges) |
| `AOA_NEWS_LIMIT` | `5` | Headlines per symbol per cycle |
| `AOA_NEWS_LOOKBACK_HOURS` | `72` | News search window |

Each cycle batches multi-symbol quote and bar requests (7 timeframes × 1 batch per
universe) and caches results for the duration of the cycle.

### Aaron's iPhone alerts

When Aaron cannot fix an issue or needs your verification first, he sends a push
notification to your **iPhone** (never email). **Recommended: your custom app.**

#### Custom app (recommended)

Point Aaron at your app's backend webhook. Aaron POSTs JSON; your server forwards
to APNs and delivers to your iPhone app:

```bash
AOA_CUSTOM_APP_WEBHOOK_URL=https://your-server.example.com/aoa/alerts
AOA_CUSTOM_APP_API_KEY=your_shared_secret      # optional Bearer token
AOA_CUSTOM_APP_DEVICE_ID=iphone-install-id     # optional routing
```

Example payload your webhook receives:

```json
{
  "source": "aoa-financial",
  "title": "AOA — Aaron (CEO)",
  "message": "[Bob/broker] Broker unreachable …",
  "reason": "unfixable",
  "requires_response": false,
  "priority": "high",
  "device_id": "iphone-install-id"
}
```

When `reason` is `needs_verification`, set `requires_response` to true in your app
so the user can confirm before the swarm proceeds.

#### Alternatives

- **Pushover** — `AOA_PUSHOVER_USER_KEY` + `AOA_PUSHOVER_APP_TOKEN` ([pushover.net](https://pushover.net))
- **ntfy** — `AOA_NTFY_TOPIC` ([ntfy.sh](https://ntfy.sh))

Aaron will attempt fixes first (broker retries, cache clears, re-running team
members) before escalating.

---

## Web dashboard & API

Install the optional web dependencies, then start the server:

```bash
pip install -e ".[web]"
aoa serve
```

Open **http://localhost:8080/** for the dashboard. REST endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Liveness check |
| `/api/status` | GET | Account, positions, loop state |
| `/api/config` | GET | Trading mode, universe, cadence |
| `/api/journal?n=30` | GET | Tail the audit log |
| `/api/run` | POST | Trigger one team-coordinated swarm cycle |
| `/api/loop/start` | POST | Start background loop |
| `/api/loop/stop` | POST | Stop background loop |
| `/api/last-cycle` | GET | Most recent cycle result |
| `/api/docs` | GET | OpenAPI interactive docs |

Set `AOA_WEB_AUTO_LOOP=true` to run the team trading loop automatically in the
background while the web server is up.

---

## Docker deployment

```bash
cp .env.example .env   # fill in API keys; AOA_ENV selects the journal subdir
docker compose up web  # dashboard at http://localhost:8080
```

Both `web` and `swarm` services share the same journal via the `aoa-data` volume
at `/app/data/{AOA_ENV}/journal/aoa.jsonl`. Set `AOA_ENV=paper-dry` in `.env`
(or use a profile) so CLI runs on the host and containerized services write to
the same logical environment.

Run the headless trading loop as a separate daemon:

```bash
docker compose --profile daemon up -d   # starts web + swarm services
```

Runtime state is persisted in the Docker volume `aoa-data` (mapped to
`/app/data` in containers).

---

## Production (systemd)

Copy the unit files and enable the services you need:

```bash
sudo cp deploy/aoa-swarm.service deploy/aoa-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aoa-web.service    # dashboard
sudo systemctl enable --now aoa-swarm.service  # headless loop
```

Adjust `User`, `WorkingDirectory`, and paths in the unit files for your host.
Create the data directory and ensure the service user can write to it:

```bash
sudo mkdir -p /var/lib/aoa/data
sudo chown aoa:aoa /var/lib/aoa/data
```

Set `AOA_ENV` (or `AOA_PROFILE`) in `.env` so web and swarm share the same
journal at `/var/lib/aoa/data/{AOA_ENV}/journal/aoa.jsonl`.

---

## News feed

When `AOA_NEWS_ENABLED=true` (the default), the **Analyze** pipeline stage fetches
recent headlines from Alpaca's market-data news API for each scanner candidate and
passes them to the **Fundamental** agent. If the feed is unavailable the agent
falls back to qualitative reasoning without fabricating headlines.

---

## Full-stack architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI (aoa doctor/status/run/loop/serve/journal)                 │
│  Web dashboard + REST API (aoa serve)                             │
└────────────────────────────┬────────────────────────────────────┘
                             │ Config.from_env()
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  TeamOrchestrator — Bob gate → Tom/Julie/Alan → trading pipeline │
│  intake → scan → analyze(+news) → mesh → portfolio → risk       │
└──────┬──────────────────┬──────────────────┬────────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
  Alpaca broker      Claude LLM         Journal (JSONL)
  (data + orders)    (agent reasoning)  + SwarmEnvironment
```

---

## Project layout

```
src/aoa/                   # live trading swarm (primary package)
  config.py                # env-driven configuration + risk limits
  brokerage/               # broker abstraction (base) + Alpaca impl + neutral models
  data/                    # market-data assembly + pure-Python indicators
  simulation/              # trend analysis, scenario library, Monte-Carlo + live tracker
  llm/                     # Anthropic Claude wrapper (adaptive thinking, structured output)
  adapt/                   # LoRA: online signal recalibration + optional torch LoRA
  agents/                  # scanner, technical, fundamental, meshing, options, portfolio, risk
  team/                    # Tom, Julie, Bob, Alan, Aaron + team orchestrator
  notify/                  # iPhone push (custom app webhook, Pushover, ntfy)
  swarm/                   # blackboard, environment, events, pipeline, stages, orchestrator
  risk/                    # deterministic cash-account guardrails
  execution/               # proposal → broker order
  journal/                 # append-only JSONL audit log (legacy default path)
  cli.py                   # `aoa` command-line entry point
  web/                     # FastAPI dashboard + REST API + loop runner

aoa_financial/             # optional deep analysis & forecasting (no live orders)
  config.py                # central configuration
  databases/               # SQLite schema + data-access layer
  ingest/                  # synthetic generator, Stooq loader, live fundamentals feed
  analysis/                # technical, fundamentals, forecast, regimes, factors, sentiment
  analysis/frames.py       # optional pandas layer: DataFrame/CSV IO, correlation panel
  llm/                     # Claude Opus 4.8 analyst (+ offline fallback)
  swarm/                   # specialist agents + decision aggregator
  backtest/                # walk-forward, lookahead-free backtest harness
  cli.py / __main__.py     # command-line interface

profiles/                  # environment profiles (paper-dry, paper, live, …)
data/                      # per-environment runtime state (gitignored)
tests/                     # pytest suite (src/aoa) + unittest suite (aoa_financial)
examples/run_demo.py       # aoa_financial end-to-end demonstration
deploy/                    # systemd unit files for production
Dockerfile                 # container image
docker-compose.yml         # web + optional swarm daemon
```

The broker layer is an abstract interface (`aoa.brokerage.base.Broker`), so a
different brokerage (Interactive Brokers, Tradier, …) can be added without
touching agent or orchestration code.

## Test

```bash
ruff check .
pytest                                    # src/aoa trading swarm (pytest)
python -m unittest discover -s tests -v # aoa_financial core (unittest, offline)
```

The trading-swarm suite runs end-to-end against an in-memory fake broker and a
canned-response fake LLM — no network, no API keys, no real orders. The
`aoa_financial` suite covers numeric primitives, the synthetic generator, every
analysis model, and the full decision pipeline with persistence (stdlib-only,
`AOA_FORCE_OFFLINE=1`).

## Low-rank adaptation (LoRA)

The agents reason through a **frozen, hosted model** (Claude via the API), so we
can't fine-tune their weights directly. Instead the swarm applies the LoRA idea
one level up — a tiny, trainable **low-rank correction on top of each agent's raw
conviction**, learned online from realized outcomes. It lives in `aoa.adapt`:

- **`aoa.adapt.lowrank.LowRankAdapter`** — a dependency-free (no torch/numpy)
  low-rank adapter implementing `ΔW = (α/r)·A·B`, with SGD training and JSON
  persistence. `A` starts at zero, so the adapter begins as an exact **no-op**
  and only departs from the agents' output as it learns.
- **`aoa.adapt.signal_adapter.SignalAdapter`** — the trading application: it
  recalibrates each signal's conviction and learns a calibration target from the
  realized move (confident-and-correct is rewarded; confident-and-wrong is
  deflated). Wired optionally into the `Orchestrator`.
- **`aoa.adapt.torch_lora`** — an optional, reusable PyTorch `LoRALinear`
  (merge/unmerge, adapter save/load, `mark_only_lora_as_trainable`) that **other
  projects** can import for real neural-net fine-tuning. Requires the extra:
  `pip install "aoa-financial[torch]"`.

Enable the swarm's online recalibration with `AOA_ADAPT_ENABLED=true` (it starts
as a no-op and improves over cycles; learned state persists to `AOA_ADAPT_PATH`).

```python
# Reusable PyTorch LoRA for any project:
from torch import nn
from aoa.adapt.torch_lora import LoRALinear, mark_only_lora_as_trainable

model = LoRALinear.from_linear(nn.Linear(768, 768), rank=8, alpha=16)
mark_only_lora_as_trainable(model)   # train just the adapter
model.merge()                        # fold the delta in for fast inference
```

## Extending

- **Add a broker**: implement `aoa.brokerage.base.Broker` and swap it in `cli.build_broker`.
- **Add a news feed**: implement `aoa.data.news.NewsFeed` and pass it to `Orchestrator`
  (or enable the built-in Alpaca feed via `AOA_NEWS_ENABLED`).
- **Add an agent**: subclass `aoa.agents.base.Agent`, register it in `AgentTeam`
  (`aoa.swarm.team`), and add or extend a pipeline stage in `aoa.swarm.stages`.
- **Customize the pipeline**: pass a custom `Pipeline(stages=[...])` to
  `Orchestrator`, or use `run_until("portfolio")` to pause for environment edits.
- **Edit the cycle environment**: use `blackboard.environment.edit_meshed()` for unified
  per-symbol overrides, or `edit_domain()` to patch a specific specialist slice.
- **Tune risk**: adjust the `AOA_*` limits in `.env` (or `RiskLimits` defaults).
- **Add a UI panel**: extend `aoa/web/app.py` dashboard or add API routes.
- **Adapt signals**: enable LoRA-style conviction recalibration with `AOA_ADAPT_*`,
  or reuse `aoa.adapt.torch_lora.LoRALinear` for neural-net fine-tuning elsewhere.

```python
from aoa.swarm.pipeline import Pipeline
from aoa.swarm.stages import default_stages, PortfolioStage

custom = Pipeline(stages=default_stages()[:3] + [PortfolioStage()] + default_stages()[4:])
orch = Orchestrator(config, broker, llm, pipeline=custom)
```

## Disclaimer

This is software for research and education. Trading stocks and options involves
substantial risk of loss. The authors make no warranty and accept no liability
for any losses incurred. Use at your own risk, and prefer the paper sandbox.
