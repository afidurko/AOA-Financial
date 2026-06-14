# AOA-Financial

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

## Project layout

```
aoa_financial/
  config.py                 # central configuration
  databases/                # SQLite schema + data-access layer
  ingest/                   # synthetic generator, Stooq loader,
                            #   provider-agnostic live fundamentals feed
  analysis/                 # technical, fundamentals, forecast, regimes,
                            #   factors, sentiment, reverse_engineer
  analysis/frames.py        # optional pandas layer: DataFrame/CSV IO,
                            #   vectorised indicators, correlation panel
  llm/                      # Claude Opus 4.8 analyst (+ offline fallback)
  swarm/                    # specialist agents + decision aggregator
  cli.py / __main__.py      # command-line interface
tests/test_core.py          # stdlib test suite
examples/run_demo.py        # end-to-end demonstration
```
