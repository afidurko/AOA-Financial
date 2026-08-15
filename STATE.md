# Loop State — AOA-Financial

Last run: 2026-08-15 21:05 UTC (issues fix + workspace integration)

## High Priority (loop is acting or waiting on human)

- **Rotate exposed API keys** — Revoke Anthropic / Alpaca paper keys in each console; update `.env` locally.  
  Source: `backlog` | Skill: `human` | id: `upg-002`

## Watch List

- **Alpaca credentials for paper** — `profiles/paper.env` uses `AOA_BROKER=alpaca` (needs keys in `.env`); `paper-dry` defaults to Moomoo + OpenD (`profiles/paper-dry.env`)
- **Runtime env partial** — fresh clones: `cp .env.example .env` + `./scripts/knowledge-stack-setup.sh` (see docs/how-to/fresh-clone.md + workspace-mesh.md)
- **L2 promotion pending** — daily triage still L1; see docs/loop-l2-checklist.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime → [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- **Task chain automated** — `aoa tasks chain advance --complete <id>` queues next item; alerts only on human-only blockers
- **Workspaces** — `aoa workspaces setup` then open `AOA.code-workspace`; VisualHFT Positions empty → [docs/how-to/visualhft-positions-orders.md](docs/how-to/visualhft-positions-orders.md)
- **VisualHFT Plugin Manager (upstream #29)** — large enhancement; track [visualHFT/VisualHFT#29](https://github.com/visualHFT/VisualHFT/issues/29) (not AOA-blocking)

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
