# Fresh clone setup

Use this checklist after cloning AOA-Financial for the first time.

## 1. Environment file

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

- `ANTHROPIC_API_KEY` — Claude API access for agent reasoning
- `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` — paper trading (keep `ALPACA_LIVE=false`)

See `.env.example` for workloop, cycle timing, and optional extras.

## 2. Install

**Trading swarm + web dashboard (recommended):**

```bash
pip install -e ".[dev,web]"
```

**Core-only (CLI without FastAPI dashboard):**

```bash
pip install -e ".[dev]"
```

Bob's import sweep treats `aoa.web.app` as optional when the `[web]` extra is not installed.

## 3. Verify

```bash
python3 -m ruff check src tests
python3 -m pytest -q
python3 -m aoa.cli doctor --offline
```

With API keys configured:

```bash
python3 -m aoa.cli doctor
```

## 4. Loop engineering (optional)

Daily triage is **L1 report-only** by default. See:

- [LOOP.md](../LOOP.md) — cadence and run order
- [loop-constraints.md](../loop-constraints.md) — binding guardrails
- [docs/safety.md](safety.md) — agent safety policy
- [docs/loop-l2-checklist.md](loop-l2-checklist.md) — promoting to L2 auto-fix

State lives in [STATE.md](../STATE.md); run history in [loop-run-log.md](../loop-run-log.md).

## 5. Work loop (optional)

Self-improvement loop (separate from daily triage):

```bash
aoa workloop status
aoa workloop run --dry-run
```

Merge and execute require Aaron approval: `aoa workloop approve`.

See [README.md](../README.md#work-loop) for operator commands.
