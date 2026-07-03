---
name: loop-budget
description: Check token budget and run-log spend before and after a loop run. Enforces early exit when over budget or when there is no actionable work.
---

# Loop Budget Guard

Run at the **start** and **end** of every loop iteration.

## Start of run

1. Read `loop-budget.md` for daily caps and kill-switch flags.
2. Read recent entries in `loop-run-log.md` (last 24h).
3. Estimate token spend from run count and outcome (L1 triage ≈ low thousands).
4. If spend ≥ 80% of the pattern's daily cap → **report-only mode** (no sub-agents, no auto-fix).
5. If spend ≥ 100% or `loop-pause-all` is set → **exit immediately** with a one-line note in STATE.md.
6. If watchlist/state has no actionable items → **exit in <5k tokens** (do not spawn sub-agents).

## End of run

Append one row to the table in `loop-run-log.md`:

```markdown
| <ISO8601 UTC> | <pattern-id> | L1/L2/L3 | <outcome> | <brief notes; optional tokens_estimate=N> |
```

Example:

```markdown
| 2026-07-03 21:28 | daily-triage | L1 | report-only | No new CI failures. tokens_estimate=4000 |
```

## Rules

- Never exceed `max sub-agent spawns/run` from `loop-budget.md`.
- High-cadence patterns (CI Sweeper, PR Babysitter) **must** early-exit when nothing is actionable.
- On self-throttle, append a line to `loop-budget.md` under **Alerts This Period**.
