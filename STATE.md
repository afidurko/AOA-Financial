# Loop State — AOA-Financial

Last run: 2026-08-15 20:50 UTC (Moomoo skills integrated + broker fixes)

## High Priority (loop is acting or waiting on human)

- **Start Moomoo OpenD** — runtime path is Moomoo. OpenD still required on `127.0.0.1:11111`. Use `/install-moomoo-opend` skill or `aoa setup moomoo`, then `aoa doctor && aoa run`. (~S)
- **Set real ANTHROPIC_API_KEY** — template key blocks LLM reasoning (~S)
- **Workloop discover→upgrade→verify pipeline** — Document and schedule periodic dependency upgrades via workloop UpgradeStage.  
  Source: `state` | Skill: `fable-repair` | id: `095e7bfe`

## Watch List

- **Moomoo OpenD offline (cloud)** — agent host cannot run OpenD without your Moomoo login
- **Runtime env partial** — fresh clones lack `.env`; see docs/how-to/fresh-clone.md
- **L2 promotion pending** — daily triage still L1; see docs/loop-l2-checklist.md
- **Fable 5 repair active** — `aoa repair triage` + `fable-repair` skill (L2)
- **Credential split** — Fable trial = loop automation; Max 5× = setup/review; API = swarm runtime
- **Task chain automated** — `aoa tasks chain advance --complete <id>`

## Loop automation

- **L1:** enabled (report-only daily triage)
- L2: enabled — scoped to auto-fixable code-health items only (draft PR, human merge)
- Enabled on: 2026-07-08 by Aaron (scoped)
- Automation A/B/C: `aoa tasks show L1` / `L2` / `BRIEF`
- Moomoo skills: `moomooapi`, `install-moomoo-opend` (vendored under `.cursor/skills/`)

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json`

## Post-Run Critique (from last run)

- Merged main Moomoo OpenD skills (PR #66) onto this branch.
- Wired skill APIs into runtime: `MoomooNewsFeed` (`get_search_news`), protective STOP/LIMIT legs, `OrderType.MARKET`, `average_cost`/`unrealized_pl`, `get_top_movers_rank`, doctor skips Alpaca crypto on Moomoo.
- 423 tests passed.
- Still needs human: OpenD login + real Anthropic key.

---
Run log: loop-run-log.md
