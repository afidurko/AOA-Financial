# TradingAgents integration — AOA-Financial

AOA uses **two related but separate** TradingAgents layers. This document maps what
is wired in-repo versus what requires the optional upstream `tradingagents` package
(TauricResearch v0.3.0).

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Live swarm (`aoa run` / `aoa loop`) — always available                 │
│  Built-in TradingAgents-*inspired* agents (Claude via aoa.llm)          │
│  Toggle: AOA_TRADING_AGENTS_ENABLED (default true)                      │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Offline / research — optional extra                                    │
│  pip install -e ".[tradingagents]"  →  upstream TradingAgentsGraph      │
│  Entry: scripts/tradingagents_propagate.py                              │
└─────────────────────────────────────────────────────────────────────────┘
```

The live pipeline **does not import** the upstream `tradingagents` package. It
implements the paper's multi-agent *pattern* (four analysts → bull/bear research →
risk debate → fund manager) using AOA's own agents and Alpaca/Moomoo data feeds.

## Built-in swarm (`AOA_TRADING_AGENTS_ENABLED`)

| Component | AOA module | Journal events | Config |
|-----------|------------|----------------|--------|
| News analyst | `aoa.agents.news_analyst` | `analyst.report` | `AOA_NEWS_*` |
| Sentiment analyst | `aoa.agents.sentiment` | `analyst.report` | headlines from broker news |
| Technical / Fundamental | existing swarm agents | (meshing) | standard AOA |
| Research team (bull/bear) | `aoa.agents.research` | `research.debate` | `AOA_TRADING_AGENTS_DEBATE_ROUNDS` |
| Risk debate | `aoa.agents.risk_debate` | `risk.debate` | runs when proposals exist |
| Fund manager | `aoa.agents.fund_manager` | `fund_manager.review` | final veto before execute |
| Portfolio context | `aoa.agents.portfolio` | `portfolio.decision` | receives `analyst_reports` + research |

Pipeline stages: `analyze` (per-symbol) → `portfolio` → `materialize` → `risk` →
`risk_debate` → `fund_manager` → `execute`. See `src/aoa/swarm/stages.py`.

Disable the extra layer without touching upstream:

```bash
export AOA_TRADING_AGENTS_ENABLED=false
```

Tests: `tests/test_trading_agents.py` (always run in CI).

## Optional upstream package (v0.3.0)

Install:

```bash
pip install -e ".[tradingagents]"
# or Bedrock provider:
pip install -e ".[tradingagents-bedrock]"
```

Pinned in `pyproject.toml` and `requirements-tradingagents.txt` at
`TradingAgents.git@v0.3.0`. Changelog: [CHANGELOG.md](CHANGELOG.md).

| Upstream v0.3.0 feature | Wired in AOA? | How |
|-------------------------|---------------|-----|
| `TradingAgentsGraph.propagate()` | **Script only** | `scripts/tradingagents_propagate.py` |
| Provider registry (NIM, Groq, Bedrock, …) | **Upstream only** | via `TRADINGAGENTS_LLM_PROVIDER` in propagate script |
| FRED macro vendor | **Not in live swarm** | upstream graph only |
| Polymarket vendor | **Not in live swarm** | upstream graph only |
| `save_reports()` | **Not wrapped** | call upstream API directly after propagate |
| yfinance indicator window | **Benchmark script** | `scripts/test_yfinance_indicators.py` |
| LangGraph checkpoints / Redis | **Upstream only** | not used by `aoa run` |
| Verified data-access contract | **Upstream only** | AOA uses Alpaca/Moomoo brokers instead |

### Env bridge (propagate script)

`scripts/tradingagents_propagate.py` loads AOA profiles/`.env` and maps:

| AOA env | Upstream default when unset |
|---------|----------------------------|
| `ANTHROPIC_API_KEY` | `TRADINGAGENTS_LLM_PROVIDER=anthropic` |
| `AOA_MODEL` | `TRADINGAGENTS_DEEP_THINK_LLM` / `QUICK_THINK_LLM` |
| `AOA_EFFORT` | `TRADINGAGENTS_ANTHROPIC_EFFORT` |
| `AOA_TRADING_AGENTS_DEBATE_ROUNDS` | `TRADINGAGENTS_MAX_DEBATE_ROUNDS` |

Override any upstream knob with explicit `TRADINGAGENTS_*` vars (see `.env.example`).

### Tests

| Test file | When it runs |
|-----------|--------------|
| `tests/test_trading_agents.py` | Always — built-in layer |
| `tests/test_tradingagents_upstream.py` | Import test skipped unless extra installed; script `--help` always |

## When to use which

| Goal | Use |
|------|-----|
| Paper/live trading with Alpaca or Moomoo | `aoa run` — built-in layer |
| Historical what-if on a past date | `python scripts/tradingagents_propagate.py SYM DATE` |
| Compare yfinance indicator windows | `python scripts/test_yfinance_indicators.py` |
| FRED / Polymarket / multi-provider LLM | Install upstream extra; configure `TRADINGAGENTS_*` — not in live swarm yet |

## Future work (not in scope for v0.3.0 audit)

- Surface upstream macro/Polymarket vendors inside live `analyze` stage
- Call `save_reports()` from journal export or web dashboard
- Optional hybrid: run upstream graph offline, feed summaries into plasticity memory
