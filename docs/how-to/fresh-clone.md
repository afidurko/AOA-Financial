# Fresh clone setup

Use this checklist after cloning AOA-Financial for the first time.

## 1. Environment file (automated on macOS)

**macOS one-liner** (Python 3.10+, venv, install — no `aoa` required yet):

```bash
git clone https://github.com/afidurko/AOA-Financial.git
cd AOA-Financial
bash scripts/setup_mac.sh --moomoo
```

Or manually:

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

- `ANTHROPIC_API_KEY` — Claude API access for agent reasoning
- **Moomoo OpenD** — install from [moomoo.com/download/OpenAPI](https://www.moomoo.com/download/OpenAPI/), log in, keep running on `127.0.0.1:11111`

See `SETUP-AWAITING-YOU.md`, [moomoo-setup.md](moomoo-setup.md), and run `aoa setup moomoo` (or `bash scripts/setup_moomoo_auth.sh`).

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

## 7. QM harness (optional)

Link the multiplayer agent harness ([qm](https://github.com/afidurko/qm)) from
the AOA dashboard header:

```bash
./scripts/qm-setup.sh
export AOA_QM_URL=http://localhost:8081
```

See [qm-integration.md](qm-integration.md). Other companions:
[docs/help.md](../help.md).

## 8. HFT strategy reference (optional)

Clone the C++ HFT sibling for pairs-arb / maker / MA strategy reading
([hft](https://github.com/afidurko/hft)). AOA does not run it:

```bash
./scripts/hft-setup.sh
```

See [hft-reference.md](hft-reference.md). Python idea ports:
`aoa.research.hft_patterns`.

## 9. example-hftish reference (optional)

Clone the Alpaca order-book imbalance sibling for tick-taker / level-change
reading ([example-hftish](https://github.com/afidurko/example-hftish)). AOA does
not run it:

```bash
./scripts/example-hftish-setup.sh
```

See [example-hftish-reference.md](example-hftish-reference.md). Python idea ports:
`aoa.research.hftish_patterns`.

## 10. SGX order-book reference (optional)

Clone the SGX A50 full-order-book notebooks sibling
([SGX-Full-OrderBook-Tick-Data-Trading-Strategy](https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy)).
AOA does not run the notebooks:

```bash
./scripts/sgx-orderbook-setup.sh
```

See [sgx-orderbook-reference.md](sgx-orderbook-reference.md). Python idea ports:
`aoa.research.sgx_orderbook_patterns`.
