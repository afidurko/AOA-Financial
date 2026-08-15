# Loop State — AOA-Financial

Last run: 2026-08-15 22:05 UTC (proofread + simplify + retest → merge)

## High Priority (loop is acting or waiting on human)

- **Rotate exposed API keys** — Revoke Anthropic / Alpaca paper keys in each console; update `.env` locally.  
  Source: `backlog` | Skill: `human` | id: `upg-002`

## Watch List

- **Moomoo OpenD for local paper-dry** — default `AOA_BROKER=moomoo`; cloud/CI: `AOA_BROKER=alpaca` or `aoa doctor --offline`
- **Runtime env partial** — fresh clones: `cp .env.example .env` + `./scripts/knowledge-stack-setup.sh`
- **L2 promotion pending** — see docs/loop-l2-checklist.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime
- **Task chain automated** — `aoa tasks chain advance --complete <id>`; human-only: upg-002
- **Workspaces** — `AOA.code-workspace` + `./scripts/connect-workspace.sh` for external roots

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

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json`

---
Run log: loop-run-log.md
