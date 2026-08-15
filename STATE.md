# Loop State — AOA-Financial

Last run: 2026-08-15 20:35 UTC (L2 fix upg-001 — Alpaca paper profiles)

## High Priority (loop is acting or waiting on human)

_(none — chain waiting or complete)_

## Watch List

- **Rotate exposed API keys** — revoke/regenerate in consoles; update `.env` locally. *(human only)*
- **Moomoo OpenD offline** — use OpenD or `AOA_BROKER=alpaca`
- **Runtime env partial** — see docs/how-to/fresh-clone.md
- **L2 promotion complete** — enabled (scoped auto-fixable items)
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Task chain automated** — `aoa tasks chain advance --complete <id>`
- **Draft PR #57** — upg-009 workloop upgrade (rebased; awaiting merge)
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Task chain automated** — `aoa tasks chain advance --complete <id>`
- **Draft PR #57** — upg-009 workloop upgrade (rebased; awaiting merge)

## Loop automation

- L1: enabled (report-only daily triage)
- L2: enabled (2026-08-15 — user approved Run L2)
- Task chain: `aoa tasks chain bootstrap` · backlog `docs/upgrade-backlog.json`
- Automation A prompt: `aoa tasks show L1`
- Automation B prompt: `aoa tasks show L2`
- Deterministic preflight: `aoa tasks run tier1-check` / `tier2-check`

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (8 items)

---
Run log: loop-run-log.md
