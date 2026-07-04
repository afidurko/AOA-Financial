# Loop Configuration — AOA-Financial

> Scaffolded from [afidurko/loop-engineering](https://github.com/afidurko/loop-engineering) via `npx @cobusgreyling/loop-init`.
> Loop Ready score: **100/100** (scaffold complete) — see `npx @cobusgreyling/loop-audit . --suggest`.
> **Operational level: L1 report-only** until [docs/loop-l2-checklist.md](docs/loop-l2-checklist.md) is complete and a human approves L2.

## Loop run order

Every daily triage run:

```
loop-constraints → loop-budget (start) → loop-triage → STATE.md + loop-run-log.md → loop-budget (end)
```

L2 adds (one item per run):

```
… → minimal-fix → loop-verifier → draft PR (human merge)
```

## Active Loops

| Pattern | Cadence | Status | Command |
|---------|---------|--------|---------|
| Daily Triage | 1d | L1 report-only | Cursor Agent or Cloud Automation (below) |
| Trading swarm | `AOA_CYCLE_SECONDS` | existing | `aoa loop` / `LoopRunner` in web |
| Work loop | `AOA_WORKLOOP_INTERVAL_SECONDS` | existing | `aoa workloop loop` |

## Cursor automation (week one — report only)

In Cursor → Automations (or Cloud Agent on schedule):

```text
Run the loop-triage skill on AOA-Financial.
Read STATE.md and LOOP.md first.
Follow loop run order in LOOP.md (constraints → budget → triage → state + run-log).
Respect loop-constraints.md and existing skills (coding-engineer, loop-*).
Do not open PRs or modify source code in week one (L1).
Flag anything ambiguous or high-risk for human review.
```

Manual equivalent: invoke the `loop-triage` skill in Agent chat on your chosen cadence.

## Human Gates

- No auto-fix until L2 checklist complete ([docs/loop-l2-checklist.md](docs/loop-l2-checklist.md); `loop-verifier` required for code changes).
- Trading / live paths: never auto-merge; `AOA_LIVE_ACK` required for live env.
- Workloop execute/merge: requires Aaron approval (`aoa workloop approve`).

## Budget

- Max sub-agent spawns per run: 0 (L1) / 2 (L2)
- Max tokens/day: 100k (see `loop-budget.md`)
- Append each run to `loop-run-log.md` (markdown table); use `loop-budget` skill at start/end
- Safety reference: `docs/safety.md`
- Kill switch: `loop-pause-all` label or flag in `STATE.md` High Priority

## Run log schema (`loop-run-log.md`)

| Column | Allowed values |
|--------|----------------|
| Timestamp (UTC) | ISO8601, e.g. `2026-07-04 12:00` |
| Loop | `daily-triage`, `trading-swarm`, `workloop`, or `maintenance` (hygiene/review runs) |
| Level | `L1`, `L2`, `L3`, or `—` for non-level maintenance |
| Outcome | `report-only`, `acted`, `exit-budget`, `exit-pause`, `merged-prep`, etc. |
| Notes | Brief; optional `tokens_estimate=N` |

Prefer `daily-triage` + `L1`/`L2` for triage runs. Use `maintenance` for git hygiene or PR review prep.

## Skills (Cursor)

| Skill | Path |
|-------|------|
| loop-constraints | `.cursor/skills/loop-constraints/SKILL.md` |
| loop-budget | `.cursor/skills/loop-budget/SKILL.md` |
| loop-triage | `.cursor/skills/loop-triage/SKILL.md` |
| minimal-fix | `.cursor/skills/minimal-fix/SKILL.md` |
| loop-verifier | `.cursor/skills/loop-verifier/SKILL.md` |
| coding-engineer | `.cursor/skills/coding-engineer/SKILL.md` |

## Links

- Fork: [github.com/afidurko/loop-engineering](https://github.com/afidurko/loop-engineering)
- Upstream: [github.com/cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering)
- Pattern: [daily-triage](https://github.com/cobusgreyling/loop-engineering/blob/main/patterns/daily-triage.md)
- Cursor example: [examples/cursor/daily-triage.md](https://github.com/cobusgreyling/loop-engineering/blob/main/examples/cursor/daily-triage.md)
- L2 promotion: [docs/loop-l2-checklist.md](docs/loop-l2-checklist.md)
