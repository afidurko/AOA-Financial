# Loop State — AOA-Financial

Last run: 2026-08-15 20:31 UTC (advisor-failure verify + STATE update; L1)

## High Priority (loop is acting or waiting on human)

- **Advisor blocked: Moomoo OpenD + API key** — `aoa doctor` fails: OpenD `ECONNREFUSED` at `127.0.0.1:11111`; `.env` has template `ANTHROPIC_API_KEY=sk-ant-...` (passes validate, LLM 401). Next: start OpenD **or** `AOA_BROKER=alpaca` + real Anthropic/Alpaca keys; then `aoa doctor && aoa run` (~S)
- **Workloop discover→upgrade→verify pipeline** — Document and schedule periodic dependency upgrades via workloop UpgradeStage.  
  Source: `state` | Skill: `fable-repair` | id: `095e7bfe`

## Watch List

- **Moomoo OpenD offline** — OpenD not running; doctor fails fast (~3s) with clear error (improved vs Jul hang); stock data needs OpenD or Alpaca (~S)
- **Placeholder Anthropic key** — non-empty template bypasses `Config.validate()`; agents still cannot reason until a real key is set (~S)
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

- **Verified 2026-08-15:** Advisor failure is environmental, not code. `tier1-check` OK; doctor fails on Moomoo OpenD with a clear fast-fail message.
- **Root causes still active:** `AOA_BROKER=moomoo` without OpenD; Anthropic key is template/`sk-ant-...` (empty key before `.env` copy also blocks LLM).
- **Platform improvement since Jul 6:** OpenD check no longer hangs on long SDK retries — doctor returns `Broker check failed: Moomoo OpenD unreachable...`.
- **Not a failure:** market-closed / 0-candidate cycles are normal (last good Alpaca run 2026-07-04).
- **Human next:** real `ANTHROPIC_API_KEY` + either OpenD or Alpaca paper path.

---
Run log: loop-run-log.md
