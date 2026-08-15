# Loop State — AOA-Financial

Last run: 2026-07-08 02:45 UTC (L2 fix upg-009 — workloop upgrade pipeline)

## High Priority (loop is acting or waiting on human)

- **Default paper profiles to Alpaca broker** — Set AOA_BROKER=alpaca in profiles/paper-dry.env and profiles/paper.env.  
  Source: `upgrade-backlog` | Skill: `minimal-fix` | id: `upg-001`

## Watch List

- **Moomoo OpenD offline** — OpenD not running at `127.0.0.1:11111`; `aoa doctor` now fails fast (~3s) with clear error; stock data still needs OpenD or `AOA_BROKER=alpaca` (~S)
- **Runtime env partial** — fresh clones lack `.env`; see docs/how-to/fresh-clone.md
- **L2 promotion pending** — daily triage still L1; see docs/loop-l2-checklist.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime → [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- **Task chain automated** — `aoa tasks chain advance --complete <id>` queues next item; alerts only on human-only blockers

## Loop automation

- **L1:** enabled (report-only daily triage)
- L2: enabled — scoped to auto-fixable code-health items only (draft PR, human merge)
- L2 scope: never auto-fix items needing CEO approval, higher escalation, or manual user notification (see [loop-constraints.md](loop-constraints.md)); those stay flagged in High Priority for a human
- Enabled on: 2026-07-08 by Aaron (scoped)
- Task chain: `aoa tasks chain bootstrap` · backlog `docs/upgrade-backlog.json`
- Automation A prompt: `aoa tasks show L1`
- Automation B prompt: `aoa tasks show L2`
- Automation C prompt: `aoa tasks show BRIEF` (daily user brief + response routing, L1)
- Deterministic preflight: `aoa tasks run tier1-check` / `tier2-check`

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (7 items)

---
Run log: loop-run-log.md
