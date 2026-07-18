# Loop Configuration — AOA-Financial (ATTL Auto-12 meshed)

> Scaffolded from [afidurko/loop-engineering](https://github.com/afidurko/loop-engineering).
> **Operating mode: ATTL `auto-12`** — Hard Safety Floor + critical-only review (Kai).
> See [docs/design/agentic-task-team-loop.md](docs/design/agentic-task-team-loop.md).

## Loop run order

Every daily triage run:

```
loop-constraints → loop-budget (start) → loop-triage → STATE.md + vault sync + loop-run-log.md → loop-budget (end)
```

Meshed L2 / coding (prefer one command):

```
aoa attl run
  → Nova brain sync → repair gate → Reed propose → Kai critical gate
  → worktree (when l2-allowed) → maker → verifier → draft PR (human merge)
```

## Active loops

| Pattern | Cadence | Level | Command / skill |
|---------|---------|-------|-----------------|
| Daily triage | 1d | L1 | `loop-triage` skill |
| **Vault sync** | 1d / per-cycle | L1 | `aoa vault sync` · tier1 `vault-sync` step |
| **ATTL mesh** | on-demand / 1d | L2-auto | `aoa attl run` · `fable-repair` |
| **Fable 5 repair** | inside ATTL | L2 | `aoa repair triage` + worktree |
| Trading swarm | `AOA_CYCLE_SECONDS` | prod | `aoa loop` / web `LoopRunner` |
| Work loop | `AOA_WORKLOOP_INTERVAL_SECONDS` | gated | `aoa workloop loop` |
| **Second brain** | per ATTL run | L1/L2 | `aoa attl brain sync` · `brain/` |

## Meshed harness

```
 Constraints (hard floor + auto-12)
        │
        ▼
 brain/ (Nova) ──► algorithms (Julie) ──► vault/brain/mesh.md
        │
        ▼
 Reed propose ← repair queue + backlog
        │
        ▼
 Kai critical-only? ──yes──► report / BRIEF
        │ no
        ▼
 worktree → maker → verifier → draft PR
```

### Repair workflow (via ATTL)

```bash
aoa attl run                   # meshed cycle (preferred)
aoa repair triage              # discover only
aoa attl propose               # Reed need-ordered tasks
python3 -m ruff check src tests && python3 -m pytest -q
# maker: minimal-fix → checker: loop-verifier when verifying a PR
```

## Scheduled automations (Tier 1 + Tier 2)

Full prompts, cron examples, and gate logic: [docs/how-to/loop-automation-schedule.md](docs/how-to/loop-automation-schedule.md)

Preflight before every automation run:

```bash
python3 -m aoa.cli repair gate --for triage
python3 -m aoa.cli repair gate --for repair --json
python3 -m aoa.cli tasks list
python3 -m aoa.cli tasks run tier1          # deterministic Tier 1
python3 -m aoa.cli tasks show L1            # copy Cloud Agent prompt
```

| Automation | Cadence | Runs when |
|------------|---------|-----------|
| **A — Daily sense** | Daily 14:00 UTC | Always (unless `loop-pause-all`) |
| **B — L2 fix** | Daily 15:00 UTC | Gate = `l2-allowed`; auto-fixable (non-escalation) items only |
| **C — User brief** | Daily 14:30 UTC | Always (unless `loop-pause-all`); `aoa loop brief --push` |

Enable L2 automation after checklist sign-off — add `L2: enabled` under `## Loop automation` in `STATE.md`.

## Human gates

- No auto-fix until L2 checklist complete ([docs/loop-l2-checklist.md](docs/loop-l2-checklist.md))
- Maker/checker split required (never self-verify)
- Trading / live: `AOA_LIVE_ACK` required; loops never submit live orders
- Workloop merge: `aoa workloop approve` (Aaron)

## Budget & safety

- Caps: `loop-budget.md` | Kill switch: `loop-pause-all` in `STATE.md`
- Run log: `loop-run-log.md` | Safety: `docs/safety.md` | Constraints: `loop-constraints.md`

## Run log schema (`loop-run-log.md`)

| Column | Allowed values |
|--------|----------------|
| Timestamp (UTC) | ISO8601 |
| Loop | `daily-triage`, `fable-repair`, `trading-swarm`, `workloop`, `maintenance` |
| Level | `L1`, `L2`, `L3`, or `—` |
| Outcome | `report-only`, `fix-proposed`, `merged-prep`, etc. |
| Notes | Brief; optional `tokens_estimate=N` |

## Skills (Cursor)

| Skill | Role |
|-------|------|
| `loop-constraints` | Hard floor + auto-12 (runs first) |
| `loop-budget` | Token / run caps |
| `loop-triage` | L1 signal → `STATE.md` |
| `fable-repair` | Repair orchestrator (meshed into ATTL) |
| `minimal-fix` | Maker — smallest diff |
| `loop-verifier` | Checker when verifying a PR / Kai path |
| `coding-engineer` | Twelve-member code-health patterns |

## Credential split (Fable trial vs Max 5× vs API)

Scheduled task routing: [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)

- **Fable 5 trial (Cloud Agent)** — daily triage, repair triage, one L2 fix/run, draft PRs; capped in `loop-budget.md`.
- **Claude Max 5×** — setup, PR review, interactive Claude Code / gstack; does not power `aoa run`.
- **Anthropic API** — swarm runtime only (`ANTHROPIC_API_KEY` in `.env`).

## Agentic Task-Team Loop (ATTL) — auto-12

Design + runtime: [docs/design/agentic-task-team-loop.md](docs/design/agentic-task-team-loop.md)

- **Mode:** `auto-12` (default) — 12-member meshed team
- **Review:** critical-only (Kai) — critical flaw / system failure / `aoa attl report`
- **Second brain:** `brain/` meshed into vault + Julie algorithms
- **CLI:** `aoa attl init|status|roster|propose|run|report|brain sync`

Cross-repo aids: loop-engineering, spine, obsidian-second-brain, AutoHedge.

## Links

- Fork: [github.com/afidurko/loop-engineering](https://github.com/afidurko/loop-engineering)
- Fable 5: [docs/fable5-repair-loop.md](docs/fable5-repair-loop.md)
- ATTL design: [docs/design/agentic-task-team-loop.md](docs/design/agentic-task-team-loop.md)
- Operating schedule: [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- Automation schedule: [docs/how-to/loop-automation-schedule.md](docs/how-to/loop-automation-schedule.md)
- L2 promotion: [docs/loop-l2-checklist.md](docs/loop-l2-checklist.md)
- Patterns: `patterns/registry.yaml`
