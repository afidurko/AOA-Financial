# Loop State — AOA-Financial

Last run: 2026-07-07 23:49 UTC (Fable 5 repair triage, run 86349a58a85e)

## High Priority (loop is acting or waiting on human)

- **Rotate exposed API keys** — Anthropic and Alpaca paper keys were pasted in chat; revoke and regenerate in each console, then update `.env` locally. Never commit secrets.  
  Source: `state` | Skill: `fable-repair` | id: `12b34cbf`

## Watch List

- **Moomoo OpenD offline** — OpenD not running at `127.0.0.1:11111`; `aoa doctor` now fails fast (~3s) with clear error; stock data still needs OpenD or `AOA_BROKER=alpaca` (~S)
- **Runtime env partial** — fresh clones lack `.env`; see docs/how-to/fresh-clone.md
- **L2 promotion pending** — daily triage still L1; see docs/loop-l2-checklist.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime → [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- **Task loops integrated** — `aoa tasks list` · shortkeys L1/L2 · `aoa tasks run tier1`

## Loop automation

- **L1:** enabled (report-only daily triage)
- **L2:** disabled — complete [docs/loop-l2-checklist.md](docs/loop-l2-checklist.md) before enabling
- Automation A prompt: `aoa tasks show L1`
- Automation B prompt: `aoa tasks show L2`
- Automation C prompt: `aoa tasks show BRIEF` (daily user brief + response routing, L1)
- Deterministic preflight: `aoa tasks run tier1-check` / `tier2-check`

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (7 items)

## Post-Run Critique (from last run)

- **Repair fix shipped:** Moomoo broker TCP probe — doctor/health no longer hang when OpenD is down.
- **Human still required:** rotate API keys (denylist — loop cannot touch `.env`).
- **CI:** 344 passed, ruff clean.
- **L2 gate:** automation still L1-only per `docs/loop-l2-checklist.md`; fix applied on user-requested repair run.

---
Run log: loop-run-log.md
