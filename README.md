# AOA Financial — Autonomous Agentic Trading Swarm

An autonomous, multi-agent swarm that analyzes the US stock market for
opportunities and executes **stock and options** trades in a **cash account**
through a live brokerage. The brokerage ([Alpaca](https://alpaca.markets)) is
both the **information source** (quotes, bars, option chains, account, positions)
and the **order executor**. Every agent reasons with **Claude** (`claude-opus-4-8`).

> ⚠️ **This software can place real orders with real money.** It defaults to
> live trading when live Alpaca credentials are configured (`ALPACA_LIVE=true`).
> Hard, deterministic risk guardrails always apply, but **you are responsible for
> any trades it makes.** Start in the paper sandbox. Nothing here is financial
> advice.

---

## How it works

Each **cycle** runs a pipeline of specialized agents coordinated over a shared
blackboard:

```
 broker (Alpaca)
   │  account, positions, quotes, bars, option chains
   ▼
┌──────────────┐   shortlist    ┌──────────────┐   signals    ┌────────────────┐
│   Scanner    │ ─────────────▶ │  Technical   │ ───────────▶ │   Portfolio    │
│ (universe →  │                │  Fundamental │              │    Manager     │
│  candidates) │                │  Options     │              │ (synthesize →  │
└──────────────┘                └──────────────┘              │  target trades)│
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

| Agent | Role |
|-------|------|
| **Scanner** | Narrows the universe to a shortlist of the strongest setups. |
| **Technical** | Reads indicators (SMA/EMA/RSI/MACD/Bollinger/ATR/vol) → directional signal. |
| **Fundamental** | Qualitative catalyst & event-risk view (never fabricates news). |
| **Options strategist** | Proposes a cash-account-appropriate options structure from the live chain. |
| **Portfolio manager** | Synthesizes all signals + positions + account into target trades. |
| **Risk manager** | Enforces hard guardrails, then an LLM second-opinion veto. |

### Cash-account safety invariants (always enforced, deterministically)

- **No equity shorting** — a sell is only allowed to close an existing long.
- **No naked short options** — only covered calls / cash-secured puts.
- **Per-position cap** (`AOA_MAX_POSITION_PCT`).
- **Options-book cap** (`AOA_MAX_OPTIONS_PCT`).
- **Minimum settled-cash buffer** (`AOA_MIN_CASH_BUFFER_PCT`).
- **Daily-loss kill switch** (`AOA_MAX_DAILY_LOSS_PCT`) — halts new risk, still allows exits.
- **Per-cycle order cap** (`AOA_MAX_ORDERS_PER_CYCLE`).

These are pure functions of the proposal/account/limits — no LLM in the loop — so
they cannot be "talked around" by a model.

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

## Install

```bash
git clone <this repo>
cd AOA-Financial
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # or: pip install -r requirements-dev.txt
```

Requires Python 3.10+.

## Configure

```bash
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY and your Alpaca keys.
# Leave ALPACA_LIVE=false to use the paper-trading sandbox first.
```

Get free Alpaca paper keys at <https://alpaca.markets>. Options trading requires
options approval on the account (the swarm checks `options_level`).

## Run

```bash
aoa doctor     # validate config + check broker/LLM connectivity
aoa status     # show account, positions, market clock
aoa run        # run ONE analysis → decision → execution cycle
aoa loop       # run continuously on AOA_CYCLE_SECONDS cadence
aoa journal -n 30   # tail the decision/trade journal

# Market-trend analysis & scenario simulation (no LLM, no orders):
aoa analyze AAPL                       # characterize the historical trend & drawdowns
aoa simulate AAPL --paths 5000 --seed 1   # Monte-Carlo forward paths + scenario stress test
aoa simulate AAPL --method bootstrap   # block-bootstrap (keeps fat tails) instead of GBM
aoa scenarios                          # list the built-in stress-scenario library
aoa watch AAPL MSFT --interval 30      # LIVE: re-analyze & re-simulate as prices move
```

Set `AOA_DRY_RUN=true` to compute and log decisions **without submitting any
orders** — the recommended way to watch the swarm reason before letting it trade.

---

## Project layout

```
src/aoa/
  config.py            # env-driven configuration + risk limits
  brokerage/           # broker abstraction (base) + Alpaca impl + neutral models
  data/                # market-data assembly + pure-Python indicators
  simulation/          # trend analysis, scenario library, Monte-Carlo + live adaptive tracker
  llm/                 # Anthropic Claude wrapper (adaptive thinking, structured output)
  agents/              # scanner, technical, fundamental, options, portfolio, risk
  swarm/               # blackboard + orchestrator (the cycle)
  risk/                # deterministic cash-account guardrails
  execution/           # proposal → broker order
  journal/             # append-only JSONL audit log
  cli.py               # `aoa` command-line entry point
tests/                 # unit + end-to-end tests (fake broker + fake LLM)
```

The broker layer is an abstract interface (`aoa.brokerage.base.Broker`), so a
different brokerage (Interactive Brokers, Tradier, …) can be added without
touching agent or orchestration code.

## Test

```bash
pytest
```

The full swarm runs end-to-end in tests against an in-memory fake broker and a
canned-response fake LLM — no network, no API keys, no real orders.

## Extending

- **Add a broker**: implement `aoa.brokerage.base.Broker` and swap it in `cli.build_broker`.
- **Add a news feed**: wire it into `FundamentalAgent` (its prompt is the integration point).
- **Add an agent**: subclass `aoa.agents.base.Agent` and call it from the `Orchestrator`.
- **Tune risk**: adjust the `AOA_*` limits in `.env` (or `RiskLimits` defaults).

## Disclaimer

This is software for research and education. Trading stocks and options involves
substantial risk of loss. The authors make no warranty and accept no liability
for any losses incurred. Use at your own risk, and prefer the paper sandbox.
