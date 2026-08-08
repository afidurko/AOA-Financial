---
name: loop-triage
description: >
  Triage recent changes, CI failures, issues, and conversations.
  Produces a concise, actionable findings report suitable for a loop to consume.
  Writes structured output to STATE.md.
user_invocable: true
---

# Loop Triage Skill

You are an expert engineering triage agent. Your job is to produce a clean, prioritized list of things that a loop should consider acting on, then **write `STATE.md`** in the canonical format below.

## Inputs (gather before triage)

- Recent CI / test failures (last 24h)
- Open issues / Linear tickets assigned to the team
- Recent commits on main (last 24–48h)
- Any Slack / chat threads the loop has visibility into
- Current `STATE.md` (what the loop already knows about)
- **Bob code audit** (deterministic, no LLM):

```bash
python3 -m aoa.cli team health
# or: python3 -c "from aoa.team.code_engineering import run_code_quality_audit; print(run_code_quality_audit())"
```

**Elevation rules for code audit:**
- `CRITICAL` finding → **High Priority**
- `DEGRADED` finding → **Watch List**
- `OK` → note in Recent Noise if relevant, otherwise ignore

## Internal analysis (do not write verbatim to STATE.md)

For each candidate item, decide:
- Clear one-line title
- Why it matters (impact, risk, or customer pain)
- Suggested next action for the loop (e.g. "draft minimal fix in isolated worktree" at L2)
- Rough effort estimate (S/M/L)

Use this analysis to compose STATE.md bullets; do not drop next-action detail.

## Write STATE.md (required output)

Update `STATE.md` using this **exact section mapping**:

| Internal bucket | STATE.md section |
|-----------------|------------------|
| High-Priority Items | `## High Priority (loop is acting or waiting on human)` |
| Watch Items | `## Watch List` |
| Noise / Ignore | `## Recent Noise (ignored this run)` |
| State Updates + run meta | `## Post-Run Critique (from last run)` + `Last run` header |

### Header (always update)

```markdown
# Loop State — AOA-Financial

Last run: <YYYY-MM-DD HH:MM UTC> (<brief run label>; loop-triage L1|L2)
```

### Bullet format (High Priority and Watch List)

One line per item; preserve impact and next action:

```markdown
- **Title** — impact; next: <suggested action> (~effort)
```

Example:

```markdown
- **Ruff failures in src/aoa/agents** — CI blocked on main; next: minimal-fix in isolated branch (~S)
```

Use `_(none)_` under High Priority when empty.

### Kill switch

If `loop-pause-all` appears anywhere in `STATE.md` High Priority, or in `loop-budget.md` Alerts, **exit immediately** after confirming constraints — do not triage further.

Example kill-switch entry:

```markdown
- **loop-pause-all** — all loops paused; next: human clears flag in STATE.md and loop-budget.md Alerts
```

### Post-Run Critique

Summarize facts to remember for the next run (PR status changes, resolved watch items, audit outcomes). Keep to 2–5 bullets.

## Sync vault properties

After updating `STATE.md`, refresh the vault knowledge directory:

```bash
python3 -m aoa.cli vault sync
```

At L1 (report-only), vault sync runs in dry-run mode unless `L2: enabled` appears under `## Loop automation` in `STATE.md`. The command analyzes every property in `vault/` per `vault/_schema.yaml` and writes updates when allowed.

## Append loop-run-log.md

After updating STATE.md, append one row (see `loop-budget` skill):

```markdown
| <ISO8601 UTC> | daily-triage | L1|L2 | report-only|acted|exit-budget | <notes; optional tokens_estimate=N> |
```

## Rules

- Be brutally concise. The loop (and the human reading the state) will thank you.
- Only put something in High Priority if a reasonable engineer would want to know about it today.
- When in doubt, put it in Watch List or Recent Noise rather than creating work.
- Never propose architectural overhauls during triage — this skill is for signal, not invention.
- Respect `loop-constraints.md` and project skills (`coding-engineer`, `loop-*`).
- **L1:** do not open PRs or modify source code — update STATE.md and run-log only.
- **L2:** may invoke `minimal-fix` → `loop-verifier` → draft PR per `docs/loop-l2-checklist.md`.
