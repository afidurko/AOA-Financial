# Loop State — AOA-Financial

Last run: 2026-07-08 02:11 UTC (Fable 5 repair triage, run 064e83d3af53)

## High Priority (loop is acting or waiting on human)

- **Resolve FastAPI/Starlette deprecation warnings** — pytest warns on Starlette TestClient httpx vs httpx2 and alpaca-py websockets.legacy; add httpx2 to web deps and filter upstream alpaca warning.  
  Source: `state` | Skill: `fable-repair` | id: `420996c2`

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

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (8 items)

---
Run log: loop-run-log.md
