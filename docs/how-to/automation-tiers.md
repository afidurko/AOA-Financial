# Automation tiers — simulate, notify, paper, live

AOA separates **what the swarm analyzes** from **what it executes** and **what reaches your phone**. Pick a tier by profile + env flags.

## Tier overview

| Tier | Profile / env | Orders | Push alerts | Typical use |
|------|----------------|--------|-------------|-------------|
| **Simulate** | `paper-dry` (default) | None (`AOA_DRY_RUN=true`) | Off unless `AOA_NOTIFY_DRY_RUN=true` | Learn the swarm; journal-only cycles |
| **Alert** | `paper-dry` + `AOA_NOTIFY_DRY_RUN=true` | None | Yes (`[SIM]` prefix on opportunities) | Watch setups without trading |
| **Paper** | `moomoo-paper` or Alpaca paper | Simulate via broker | Per notify settings | Full loop with fake money |
| **Live** | `AOA_ENV=live` + ack | Real | Per notify settings | Production (human gate required) |

## Simulate (default)

```bash
pip install -e ".[dev,web,openai]"
cp .env.example .env
aoa loop
```

- `ensure_profile()` loads `profiles/paper-dry.env` (Moomoo + Ollama).
- `AOA_AUTO_ACTIVATE=true` waits for OpenD and verifies Ollama before cycles run.
- Opportunity pushes are **suppressed** when `AOA_DRY_RUN=true` and `AOA_NOTIFY_DRY_RUN=false` (default).
- Halts and critical alerts still push when `AOA_NOTIFY_PUSH_HALTS=true`.

## Alert-only dry-run

Edit `.env`:

```bash
AOA_NOTIFY_DRY_RUN=true
AOA_NOTIFY_MIN_CONVICTION=0.75
```

High-conviction opportunities are pushed with a `[SIM]` title prefix; no orders are submitted.

## Paper trading (broker simulate)

```bash
export AOA_PROFILE=moomoo-paper
aoa loop
```

Orders go through Moomoo OpenD simulate mode. Tune conviction:

```bash
AOA_NOTIFY_MIN_CONVICTION=0.65
AOA_NOTIFY_PUSH_OPPORTUNITIES=true
```

## Live trading

Requires explicit acknowledgement — see [SETUP-AWAITING-YOU.md](../../SETUP-AWAITING-YOU.md).

## Auto-start without typing `aoa activate`

| Entry point | Behavior |
|-------------|----------|
| `aoa loop` / `aoa run` / `aoa serve` | `auto_activate` before first cycle |
| `aoa doctor` (online) | Waits for OpenD when broker is Moomoo |
| `aoa status` | Same wait when broker is Moomoo |
| Web dashboard | `create_app` lifespan: activate → then `build_team` |

Optional always-on loop from the dashboard:

```bash
# profiles/moomoo.env or .env
AOA_WEB_AUTO_LOOP=true
```

systemd example: `deploy/aoa-swarm.service` (`ExecStart=aoa loop`, `AOA_PROFILE=paper-dry`).

## Strict activation

When `AOA_AUTO_ACTIVATE_STRICT=true` (default), `auto_activate` fails if:

- OpenD TCP is up but SPY bars are unavailable (not logged in).
- Ollama is down, the `openai` extra is missing, or the configured model is not pulled.

Disable for debugging:

```bash
export AOA_AUTO_ACTIVATE_STRICT=false
```
