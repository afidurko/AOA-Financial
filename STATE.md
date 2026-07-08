# Loop State — AOA-Financial

Last run: 2026-07-08 02:25 UTC (Fable 5 repair triage, run 4ac7089eb088)

## High Priority (loop is acting or waiting on human)

_(none — system healthy or only watch items)_

## Watch List

- **Rotate exposed API keys** — revoke/regenerate in consoles; update `.env` locally. *(human only)*
- **Moomoo OpenD offline** — use OpenD or `AOA_BROKER=alpaca`
- **Runtime env partial** — see docs/how-to/fresh-clone.md
- **L2 promotion complete** — enabled 2026-07-08
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — see docs/how-to/fable-max-operating-schedule.md
- **Task loops integrated** — `aoa tasks list` · shortkeys L1/L2

## Loop automation

- L1: enabled (report-only daily triage)
- L2: enabled (2026-07-08 — user approved Run L2)
- Automation A prompt: `aoa tasks show L1`
- Automation B prompt: `aoa tasks show L2`
- Deterministic preflight: `aoa tasks run tier1-check` / `tier2-check`

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (7 items)

---
Run log: loop-run-log.md
