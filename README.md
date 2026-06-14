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

## Project layout

```
src/aoa/
  config.py            # env-driven configuration + risk limits
  brokerage/           # broker abstraction (base) + Alpaca impl + neutral models
  data/                # market-data assembly + pure-Python indicators
  llm/                 # Anthropic Claude wrapper (adaptive thinking, structured output)
  adapt/               # Low-Rank Adaptation (LoRA): online signal recalibration + torch LoRA
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
- **Add a news feed**: wire it into `FundamentalAgent` (its prompt is the integration point).
- **Add an agent**: subclass `aoa.agents.base.Agent` and call it from the `Orchestrator`.
- **Tune risk**: adjust the `AOA_*` limits in `.env` (or `RiskLimits` defaults).
- **Adapt signals**: enable LoRA-style conviction recalibration with `AOA_ADAPT_*`,
  or reuse `aoa.adapt.torch_lora.LoRALinear` for neural-net fine-tuning elsewhere.

## Disclaimer

This is software for research and education. Trading stocks and options involves
substantial risk of loss. The authors make no warranty and accept no liability
for any losses incurred. Use at your own risk, and prefer the paper sandbox.
