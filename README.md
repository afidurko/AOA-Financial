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
   │  account, positions, quotes, multi-TF bars, news, option chains
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
| **Technical** | Multi-timeframe indicators (1m→yearly: SMA/EMA/RSI/MACD/Bollinger/ATR/vol) → signal. |
| **Fundamental** | Alpaca news headlines + catalyst/event-risk view (never fabricates news). |
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
aoa serve      # start the web dashboard + REST API (port 8080)
aoa journal -n 30   # tail the decision/trade journal
```

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
| `/api/run` | POST | Trigger one swarm cycle |
| `/api/loop/start` | POST | Start background loop |
| `/api/loop/stop` | POST | Stop background loop |
| `/api/last-cycle` | GET | Most recent cycle result |
| `/api/docs` | GET | OpenAPI interactive docs |

Set `AOA_WEB_AUTO_LOOP=true` to run the trading loop automatically in the
background while the web server is up.

---

## Docker deployment

```bash
cp .env.example .env   # fill in API keys
docker compose up web  # dashboard at http://localhost:8080
```

Run the headless trading loop as a separate daemon:

```bash
docker compose --profile daemon up -d   # starts web + swarm services
```

The journal is persisted in a Docker volume (`aoa-journal`).

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

---

## News feed

When `AOA_NEWS_ENABLED=true` (the default), the orchestrator fetches recent
headlines from Alpaca's market-data news API for each scanner candidate and
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
│  Orchestrator — one cycle pipeline                              │
│  Scanner → Technical/Fundamental(+news) → Options → PM → Risk   │
└──────┬──────────────────┬──────────────────┬────────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
  Alpaca broker      Claude LLM         Journal (JSONL)
  (data + orders)    (agent reasoning)
```

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
  web/                 # FastAPI dashboard + REST API + loop runner
tests/                 # unit + end-to-end tests (fake broker + fake LLM)
deploy/                # systemd unit files for production
Dockerfile             # container image
docker-compose.yml     # web + optional swarm daemon
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
- **Add a news feed**: implement or extend `aoa.data.news.NewsFeed` (Alpaca is built-in)
  and pass it to `Orchestrator`; tune via `AOA_NEWS_*` in `.env`.
- **Add an agent**: subclass `aoa.agents.base.Agent` and call it from the `Orchestrator`.
- **Tune risk**: adjust the `AOA_*` limits in `.env` (or `RiskLimits` defaults).
- **Add a UI panel**: extend `aoa/web/app.py` dashboard or add API routes.

## Disclaimer

This is software for research and education. Trading stocks and options involves
substantial risk of loss. The authors make no warranty and accept no liability
for any losses incurred. Use at your own risk, and prefer the paper sandbox.
