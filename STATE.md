# Loop State — AOA-Financial

Last run: 2026-07-08 02:06 UTC (L2 fix upg-005 — README/model alignment)

## High Priority (loop is acting or waiting on human)

_(none — upg-005 fix in PR)_

## Watch List

- **Rotate exposed API keys** — Anthropic and Alpaca paper keys were pasted in chat; revoke and regenerate in each console, then update `.env` locally. Never commit secrets. *(human only)*
- **Moomoo OpenD offline** — OpenD not running at `127.0.0.1:11111`; `aoa doctor` fails fast (~3s); use OpenD or `AOA_BROKER=alpaca`
- **Runtime env partial** — fresh clones lack `.env`; see docs/how-to/fresh-clone.md
- **L2 promotion complete** — enabled 2026-07-08; user approved Run L2
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime → [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- **Task loops integrated** — `aoa tasks list` · shortkeys L1/L2 · `aoa tasks run tier1`

## Loop automation

- L1: enabled (report-only daily triage)
- L2: enabled (2026-07-08 — user approved Run L2)
- Automation A prompt: `aoa tasks show L1`
- Automation B prompt: `aoa tasks show L2`
- Deterministic preflight: `aoa tasks run tier1-check` / `tier2-check`

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (8 items)

---
Run log: loop-run-log.md
