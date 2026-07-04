# Loop State — AOA-Financial

Last run: 2026-07-04 23:11 UTC (PR #36 rebased onto main after #37 merge)

## High Priority (loop is acting or waiting on human)

- **Rotate exposed API keys** — Anthropic and Alpaca paper keys were pasted in chat; revoke and regenerate in each console, then update `.env` locally. Never commit secrets.  
  Source: `state` | Skill: `fable-repair` | id: `a1fce142`

## Watch List

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

## Next actions (by owner)

| When | Owner | Task |
|------|-------|------|
| Today | **Max 5× (you)** | Rotate API keys; ntfy iPhone alerts + OpenStock + `aoa serve` |
| Daily | **Fable trial** | `aoa tasks run tier1` then paste `aoa tasks show L1` if gate allows |
| Daily +1h | **Fable trial** | `aoa tasks run tier2-check` then paste `aoa tasks show L2` if l2-allowed |
| Weekly | **Max 5×** | `aoa tasks show REVIEW` · review PR #35 if switching to Moomoo |

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (run `aoa repair triage` after STATE edits)

---
Run log: loop-run-log.md
