# Loop Configuration — AOA-Financial (Fable 5)

> Scaffolded from [afidurko/loop-engineering](https://github.com/afidurko/loop-engineering).
> **Operational level: L1 report-only** until [docs/loop-l2-checklist.md](docs/loop-l2-checklist.md) is complete and a human approves L2.

## Loop run order

Every daily triage run:

```
loop-constraints → loop-budget (start) → loop-triage → STATE.md + loop-run-log.md → loop-budget (end)
```

L2 repair (one item per run):

```
fable-repair → aoa repair triage → worktree → minimal-fix → loop-verifier → draft PR (human merge)
```

## Active loops

| Pattern | Cadence | Level | Command / skill |
|---------|---------|-------|-----------------|
| Daily triage | 1d | L1 | `loop-triage` skill |
| **Fable 5 repair** | on-demand / 1d | L2 | `aoa repair triage` + `fable-repair` skill |
| Trading swarm | `AOA_CYCLE_SECONDS` | prod | `aoa loop` / web `LoopRunner` |
| Work loop | `AOA_WORKLOOP_INTERVAL_SECONDS` | gated | `aoa workloop loop` |

## Fable 5 harness (six blocks)

```
 Automations          Worktrees              Skills
 aoa repair triage    .aoa-worktrees/        fable-repair (orchestrator)
 Cursor Automations   repair/<id> branches   minimal-fix (maker)
                                              loop-verifier (checker)
        │                    │                      │
        └──────── Connectors ─┴── State ────────────┘
              Bob audit, verify, STATE.md, repair/queue.json
```

### Repair workflow (L2)

```bash
aoa repair triage              # discover → queue.json + STATE.md (quick verify)
aoa repair queue               # list fixable items
aoa repair worktree --item-id X   # isolated branch for fix
python3 -m ruff check src tests && python3 -m pytest -q
# maker: minimal-fix → checker: loop-verifier (separate agent pass)
```

## Cursor automation (L1 triage)

```text
Run the loop-triage skill on AOA-Financial.
Read STATE.md and LOOP.md first.
Follow loop run order (constraints → budget → triage → state + run-log).
No code changes in week one (L1).
```

## Cursor automation (Fable 5 repair — L2)

```text
Run the fable-repair skill on AOA-Financial.
Read LOOP.md, loop-constraints.md, docs/safety.md.
Run aoa repair triage. Fix at most ONE queued item in a worktree.
Use minimal-fix (maker) then loop-verifier (checker) in separate contexts.
Draft PR only; never auto-merge.
```

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
| `loop-constraints` | Binding guardrails (runs first) |
| `loop-budget` | Token / run caps |
| `loop-triage` | L1 signal → `STATE.md` |
| `fable-repair` | L2 orchestrator |
| `minimal-fix` | Maker — smallest diff |
| `loop-verifier` | Checker — reject by default |
| `coding-engineer` | Bob/Julie audit patterns |

## Credential split (Fable trial vs Max 5× vs API)

Scheduled task routing: [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)

- **Fable 5 trial (Cloud Agent)** — daily triage, repair triage, one L2 fix/run, draft PRs; capped in `loop-budget.md`.
- **Claude Max 5×** — setup, PR review, interactive Claude Code / gstack; does not power `aoa run`.
- **Anthropic API** — swarm runtime only (`ANTHROPIC_API_KEY` in `.env`).

## Links

- Fork: [github.com/afidurko/loop-engineering](https://github.com/afidurko/loop-engineering)
- Fable 5: [docs/fable5-repair-loop.md](docs/fable5-repair-loop.md)
- Operating schedule: [docs/how-to/fable-max-operating-schedule.md](docs/how-to/fable-max-operating-schedule.md)
- L2 promotion: [docs/loop-l2-checklist.md](docs/loop-l2-checklist.md)
- Patterns: `patterns/registry.yaml`
