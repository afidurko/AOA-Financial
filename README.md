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
│  Orchestrator — composable pipeline (intake → … → execute)      │
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
src/aoa/
  config.py            # env-driven configuration + risk limits
  brokerage/           # broker abstraction (base) + Alpaca impl + neutral models
  data/                # market-data assembly + pure-Python indicators
  llm/                 # Anthropic Claude wrapper (adaptive thinking, structured output)
  agents/              # scanner, technical, fundamental, meshing, options, portfolio, risk
  team/                # Tom, Julie, Bob, Alan, Aaron + team orchestrator
  notify/              # iPhone push (custom app webhook, Pushover, ntfy)
  swarm/               # blackboard, environment, events, pipeline, stages, orchestrator
  risk/                # deterministic cash-account guardrails
  execution/           # proposal → broker order
  journal/             # append-only JSONL audit log (legacy default path)
  cli.py               # `aoa` command-line entry point
  web/                 # FastAPI dashboard + REST API + loop runner
profiles/              # environment profiles (paper-dry, paper, live, …)
data/                  # per-environment runtime state (gitignored)
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
ruff check .
pytest
```

The full swarm runs end-to-end in tests against an in-memory fake broker and a
canned-response fake LLM — no network, no API keys, no real orders.

## Extending

- **Add a broker**: implement `aoa.brokerage.base.Broker` and swap it in `cli.build_broker`.
- **Add a news feed**: implement or extend `aoa.data.news.NewsFeed` (Alpaca is built-in)
  and pass it to `Orchestrator`; tune via `AOA_NEWS_*` or `AOA_NEWS_ENABLED` in `.env`.
- **Add an agent**: subclass `aoa.agents.base.Agent`, register it in `AgentTeam`
  (`aoa.swarm.team`), and add or extend a pipeline stage in `aoa.swarm.stages`.
- **Customize the pipeline**: pass a custom `Pipeline(stages=[...])` to
  `Orchestrator`, or use `run_until("portfolio")` to pause for environment edits.
- **Edit the cycle environment**: use `blackboard.environment.edit_meshed()` for unified
  per-symbol overrides, or `edit_domain()` to patch a specific specialist slice.
- **Tune risk**: adjust the `AOA_*` limits in `.env` (or `RiskLimits` defaults).
- **Add a UI panel**: extend `aoa/web/app.py` dashboard or add API routes.

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
