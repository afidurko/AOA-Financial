# Loop State — AOA-Financial

Last run: 2026-07-04 18:47 UTC (Fable 5 repair triage, run 1b17b8227cbc)

## High Priority (loop is acting or waiting on human)

_(none — system healthy or only watch items)_

## Watch List

- **PR #29** — verify quick-mode fix; merge after #22
- **Runtime env partial** — fresh clones lack `.env`; see docs/how-to/fresh-clone.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime → [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)

## Next actions (by owner)

| When | Owner | Task |
|------|-------|------|
| Today | **Max 5× (you)** | `SETUP-AWAITING-YOU.md`: `ANTHROPIC_API_KEY`, Alpaca paper login, `aoa doctor`, first `aoa run` |
| Daily | **Fable trial** | L1 triage; L2 only if fixable item + budget OK |
| This week | **Max 5×** | Review PR #29; L2 checklist sign-off before more auto-fix |

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (3 items)

---
Run log: loop-run-log.md
