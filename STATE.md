# Loop State — AOA-Financial

Last run: 2026-08-15 20:35 UTC (Moomoo path locked; OpenD still required)

## High Priority (loop is acting or waiting on human)

- **Start Moomoo OpenD** — broker path is Moomoo (`AOA_BROKER=moomoo`). OpenD not listening on `127.0.0.1:11111`. On your machine: install/start OpenD ([download](https://www.moomoo.com/download/OpenAPI/)), log in, then `aoa setup moomoo && aoa doctor && aoa run`. Guides: [docs/how-to/moomoo-setup.md](docs/how-to/moomoo-setup.md), `SETUP-AWAITING-YOU.md` (~S)
- **Set real ANTHROPIC_API_KEY** — template `sk-ant-...` passes validate but LLM auth fails; agents need a real key in `.env` (~S)
- **Workloop discover→upgrade→verify pipeline** — Document and schedule periodic dependency upgrades via workloop UpgradeStage.  
  Source: `state` | Skill: `fable-repair` | id: `095e7bfe`

## Watch List

- **Moomoo OpenD offline (cloud)** — this agent host cannot run OpenD without your Moomoo login; Docker not available here. Human starts OpenD locally.
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

## Post-Run Critique (from last run)

- **Broker choice:** human selected **Moomoo** — Alpaca optional path de-emphasized in README/STATE.
- **Config verified:** `AOA_BROKER=moomoo`, profile `paper-dry`, OpenD target `127.0.0.1:11111`, `moomoo-api` installed, `aoa setup moomoo` OK offline.
- **Still blocked:** OpenD `ECONNREFUSED` (doctor fail-fast ~3s) + real Anthropic key required.
- **Cannot complete in cloud:** OpenD needs local install + Moomoo account login (no Docker on this host).

---
Run log: loop-run-log.md
