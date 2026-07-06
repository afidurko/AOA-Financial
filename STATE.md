# Loop State — AOA-Financial

Last run: 2026-07-06 03:12 UTC (full upgrade discovery + upg-001 profile fix)

## High Priority (loop is acting or waiting on human)

- **Rotate exposed API keys** — Anthropic and Alpaca paper keys were pasted in chat; revoke and regenerate in each console, then update `.env` locally. Never commit secrets.  
  Source: `state` | Skill: `fable-repair` | id: `ceabf69f`

## Watch List

- **Upgrade backlog ready** — Fable 5 queue at `docs/upgrade-backlog.json` (10 items, prioritized sequence)
- **Runtime env partial** — fresh clones lack `.env`; see docs/how-to/fresh-clone.md
- **Draft PR #35** — Moomoo broker via OpenD (hold — Alpaca paper working; re-run CI after rebase)
- **L2 promotion pending** — daily triage still L1; see docs/loop-l2-checklist.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime → [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- **Task loops integrated** — `aoa tasks list` · shortkeys L1/L2 · `aoa tasks run tier1`

## Loop automation

- **L1:** enabled (report-only daily triage)
- **L2:** disabled — complete [docs/loop-l2-checklist.md](docs/loop-l2-checklist.md) before enabling
- Automation A prompt: `aoa tasks show L1`
- Automation B prompt: `aoa tasks show L2`
- Deterministic preflight: `aoa tasks run tier1-check` / `tier2-check`

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (7 items)

---
Run log: loop-run-log.md
