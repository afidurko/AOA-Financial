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
```

Set `AOA_DRY_RUN=true` to compute and log decisions **without submitting any
orders** — the recommended way to watch the swarm reason before letting it trade.

---

## Certified financial assistant

Alongside the trader, the repo ships an **autonomous, fiduciary financial
assistant** — a CFP-style advisor you can talk to. Where the swarm *places trades*,
the assistant *gives advice*: it reasons over your whole financial picture (cash
flow, emergency fund, debt, retirement, asset allocation, tax-advantaged accounts)
and tells you what it would do and why.

It is **agentic and grounded**: every number it states comes from a deterministic,
unit-tested calculator it *calls as a tool* — it is forbidden from doing arithmetic
in its head. This keeps the math correct and auditable, exactly like the trading
swarm keeps binding risk logic out of the LLM.

```
                      ┌──────────────────────────────────────────┐
  your question ────▶ │  FinancialAdvisor  (fiduciary CFP persona)│
                      │  agentic tool-use loop over Claude         │
                      └───────────────┬──────────────────────────┘
                                      │ calls tools (never guesses numbers)
            ┌─────────────────────────┼─────────────────────────────┐
            ▼                         ▼                              ▼
   net worth / savings    debt payoff (avalanche vs       retirement projection,
   emergency fund          snowball), allocation drift,    contribution room,
                           [+ live portfolio if a broker is configured]
```

### Use it

```bash
aoa profile init     # scaffold profile/financial_profile.json — then edit it
aoa profile          # show your net worth, cash flow, debts at a glance
aoa plan             # generate a full written financial plan
aoa advise           # chat with your assistant ("how fast can I be debt-free?")
```

The assistant needs only `ANTHROPIC_API_KEY`. Your profile is a private JSON file
(git-ignored); if Alpaca keys are present it can also read your live positions for
portfolio context. It is an **educational tool, not a licensed advisor** — it gives
no individualized tax/legal/insurance advice and never promises returns.

> ⚠️ The 401(k)/IRA/HSA contribution limits in `aoa.advisor.planning` are dated
> data (2025 confirmed, 2026 per announced COLA). Verify against current IRS
> figures before relying on them.

---

## Project layout

```
src/aoa/
  config.py            # env-driven configuration + risk limits
  brokerage/           # broker abstraction (base) + Alpaca impl + neutral models
  data/                # market-data assembly + pure-Python indicators
  llm/                 # Anthropic Claude wrapper (adaptive thinking, structured output)
  agents/              # scanner, technical, fundamental, options, portfolio, risk
  advisor/             # certified financial assistant: profile, planning math,
                       #   tools (Claude tool-use), and the advisor agent
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
