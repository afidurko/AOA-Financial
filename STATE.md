# Loop State — AOA-Financial

Last run: 2026-07-04 19:27 UTC (Fable 5 repair triage, run 4ddbc7039fc1)

## High Priority (loop is acting or waiting on human)

_(none — system healthy or only watch items)_

## Watch List

- **PR #29** — verify quick-mode fix; merge after #22
- **Runtime env partial** — fresh clones lack `.env`; see docs/how-to/fresh-clone.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime → [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- **Task loops integrated** — `aoa tasks list` · shortkeys L1/L2 · `aoa tasks run tier1`

## Loop automation

- L2: disabled (enable after [docs/loop-l2-checklist.md](docs/loop-l2-checklist.md) sign-off)
- Automation A prompt: `aoa tasks show L1`
- Automation B prompt: `aoa tasks show L2`
- Deterministic preflight: `aoa tasks run tier1-check` / `tier2-check`

## Next actions (by owner)

| When | Owner | Task |
|------|-------|------|
| Today | **Max 5× (you)** | `aoa tasks show SETUP` → complete `.env`, Alpaca, `aoa doctor`, first `aoa run` |
| Daily | **Fable trial** | `aoa tasks run tier1` then paste `aoa tasks show L1` if gate allows |
| Daily +1h | **Fable trial** | `aoa tasks run tier2-check` then paste `aoa tasks show L2` if l2-allowed |
| Weekly | **Max 5×** | `aoa tasks show REVIEW` · merge draft PRs |

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (4 items)

---
Run log: loop-run-log.md
