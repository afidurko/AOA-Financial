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
aoa report     # activity summary (from journal) + live P&L snapshot
```

`aoa report` combines journal-derived **activity** (cycles, candidates, orders,
re-entry skips, and the top reasons proposals were risk-blocked) with a live
**P&L snapshot** — open-position unrealized P&L and the day's P&L versus the
persisted baseline. The live half is best-effort and is skipped with a note if
the broker isn't reachable, so the activity summary still works offline.

Set `AOA_DRY_RUN=true` to compute and log decisions **without submitting any
orders** — the recommended way to watch the swarm reason before letting it trade.

---

## Project layout

```
src/aoa/
  config.py            # env-driven configuration + risk limits
  brokerage/           # broker abstraction (base) + Alpaca impl + neutral models
  data/                # market-data assembly + pure-Python indicators
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
