# Fresh clone setup

Use this checklist after cloning AOA-Financial for the first time.

## 1. Environment file

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

- `ANTHROPIC_API_KEY` — Claude API access for agent reasoning
- **Moomoo OpenD** — install from [moomoo.com/download/OpenAPI](https://www.moomoo.com/download/OpenAPI/), log in, keep running on `127.0.0.1:11111`

See `SETUP-AWAITING-YOU.md` and run `bash scripts/setup_moomoo_auth.sh`.

**Optional Alpaca:** set `AOA_BROKER=alpaca`, `pip install -e ".[alpaca]"`, and run `bash scripts/setup_alpaca_auth.sh`.

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

## 6. OpenStock (optional)

Run the open-source [OpenStock](https://github.com/Open-Dev-Society/OpenStock) market
UI beside the swarm for charts and watchlists:

```bash
./scripts/openstock-setup.sh
./scripts/sync-openstock-env.sh
export AOA_OPENSTOCK_URL=http://localhost:3000
```

See [openstock-integration.md](openstock-integration.md) for Docker and env details.
