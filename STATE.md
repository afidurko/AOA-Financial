# Loop State — AOA-Financial

Last run: 2026-07-06 03:22 UTC (loop-triage L1; user-requested run)

## High Priority (loop is acting or waiting on human)

- **Rotate exposed API keys** — Anthropic and Alpaca paper keys were pasted in chat; revoke and regenerate in each console, then update `.env` locally. Never commit secrets.  
  Source: `state` | Skill: `fable-repair` | id: `74476c43`

## Watch List

- **Moomoo OpenD offline** — `127.0.0.1:11111` ECONNREFUSED; stock quotes and `aoa doctor` hang without OpenD running; next: start OpenD locally or switch broker to Alpaca for paper (~S)
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
- Deterministic preflight: `aoa tasks run tier1-check` / `tier2-check`

## Next actions (by owner)

| When | Owner | Task |
|------|-------|------|
| Today | **Max 5× (you)** | Rotate API keys; start Moomoo OpenD or set Alpaca broker; ntfy + OpenStock + `aoa serve` |
| Daily | **Fable trial** | `aoa tasks run tier1` then paste `aoa tasks show L1` if gate allows |
| Daily +1h | **Fable trial** | `aoa tasks run tier2-check` then paste `aoa tasks show L2` if l2-allowed |
| Weekly | **Max 5×** | `aoa tasks show REVIEW` · tune swarm weights against live journal outcomes |

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json` (7 items)

## Post-Run Critique (from last run)

- **CI local green:** ruff clean; 337 passed, 6 skipped.
- **Bob code audit:** all checks OK (pricing, web app, loop scaffold, ruff).
- **PR #35 merged** — Moomoo is now default broker on main; OpenD must be running for stock data.
- **Key rotation still open** — human-only; loop cannot touch `.env`.
- **Model-improvement path:** tune `swarm_weights` + plasticity memory from journal; run `aoa workloop` for larger cycles (Aaron gate).

## Recent Noise (ignored this run)

- websockets/fastapi deprecation warnings in test output (upstream; no action)
- `aoa team health` hangs when Moomoo OpenD unreachable — use code audit directly until OpenD up
- PR #35 watch item stale (merged) — removed from watch list

---
Run log: loop-run-log.md
