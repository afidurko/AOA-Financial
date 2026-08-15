# Loop State — AOA-Financial

Last run: 2026-08-15 22:05 UTC (ship proofread + Moomoo skill merge)

## High Priority (loop is acting or waiting on human)

- **Start Moomoo OpenD** — runtime path is Moomoo. OpenD required on `127.0.0.1:11111`. Use `/install-moomoo-opend` or `aoa setup moomoo`, then `aoa doctor && aoa run`. (~S)
- **Set real ANTHROPIC_API_KEY** — rotate any exposed keys; template key blocks LLM reasoning (~S)

## Watch List

- **Alpaca credentials for paper** — `profiles/paper.env` uses `AOA_BROKER=alpaca` (needs keys in `.env`); `paper-dry` defaults to Moomoo + OpenD (`profiles/paper-dry.env`)
- **Runtime env partial** — fresh clones: `cp .env.example .env` + `./scripts/knowledge-stack-setup.sh` (see docs/how-to/fresh-clone.md + workspace-mesh.md)
- **L2 promotion pending** — daily triage still L1; see docs/loop-l2-checklist.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime → [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- **Task chain automated** — `aoa tasks chain advance --complete <id>` queues next item; alerts only on human-only blockers
- **Workspaces** — `aoa workspaces setup` then open `AOA.code-workspace`; Cursor Cloud env via `.cursor/environment.json`; VisualHFT Positions empty → [docs/how-to/visualhft-positions-orders.md](docs/how-to/visualhft-positions-orders.md)
- **VisualHFT Plugin Manager (upstream #29)** — large enhancement; track [visualHFT/VisualHFT#29](https://github.com/visualHFT/VisualHFT/issues/29) (not AOA-blocking)

## Loop automation

- **L1:** enabled (report-only daily triage)
- L2: enabled — scoped to auto-fixable code-health items only (draft PR, human merge)
- Enabled on: 2026-07-08 by Aaron (scoped)
- Automation A/B/C: `aoa tasks show L1` / `L2` / `BRIEF`
- Moomoo skills: `moomooapi`, `install-moomoo-opend` (vendored under `.cursor/skills/`)

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json`

## Post-Run Critique (from last run)

- Moomoo OpenD skills wired into runtime; helpers simplified after proofread.
- Kept `AOA_BROKER=moomoo` (user choice) over main's alpaca paper-profile flip.
- Tests green after merge-base catch-up; OpenD + real API key still human.

---
Run log: loop-run-log.md
