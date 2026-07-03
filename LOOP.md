# Loop Configuration — AOA-Financial

> Scaffolded from [afidurko/loop-engineering](https://github.com/afidurko/loop-engineering) via `npx @cobusgreyling/loop-init`.
> Loop Ready score: **100/100 (L2)** — see `npx @cobusgreyling/loop-audit . --suggest`.

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
Append high-priority items to STATE.md (High Priority + Watch List only).
Respect loop-constraints.md and existing skills (coding-engineer, loop-*).
Do not open PRs or modify source code in week one.
Flag anything ambiguous or high-risk for human review.
```

Manual equivalent: invoke the `loop-triage` skill in Agent chat on your chosen cadence.

## Human Gates

- No auto-fix until L2 checklist complete (`loop-verifier` required for code changes).
- Trading / live paths: never auto-merge; `AOA_LIVE_ACK` required for live env.
- Workloop execute/merge: requires Aaron approval (`aoa workloop approve`).

## Budget

- Max sub-agent spawns per run: 0 (L1) / 2 (L2)
- Max tokens/day: 100k (see `loop-budget.md`)
- Append each run to `loop-run-log.md` (markdown table); use `loop-budget` skill at start/end
- Safety reference: `docs/safety.md`
- Kill switch: `loop-pause-all` label or flag in `STATE.md`

## Skills (Cursor)

| Skill | Path |
|-------|------|
| loop-triage | `.cursor/skills/loop-triage/SKILL.md` |
| loop-budget | `.cursor/skills/loop-budget/SKILL.md` |
| loop-constraints | `.cursor/skills/loop-constraints/SKILL.md` |
| loop-verifier | `.cursor/skills/loop-verifier/SKILL.md` |
| coding-engineer | `.cursor/skills/coding-engineer/SKILL.md` |

## Links

- Fork: [github.com/afidurko/loop-engineering](https://github.com/afidurko/loop-engineering)
- Upstream: [github.com/cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering)
- Pattern: [daily-triage](https://github.com/cobusgreyling/loop-engineering/blob/main/patterns/daily-triage.md)
- Cursor example: [examples/cursor/daily-triage.md](https://github.com/cobusgreyling/loop-engineering/blob/main/examples/cursor/daily-triage.md)
