# Loop automation schedule — Tier 1 + Tier 2

Self-sustaining **engineering** loops for AOA-Financial: sense daily, fix only when the queue says so, never merge without you.

Related: [fable-max-operating-schedule.md](fable-max-operating-schedule.md) | [LOOP.md](../../LOOP.md) | `loop-budget.md`

---

## Overview

| Tier | When | What runs | Code changes? |
|------|------|-----------|---------------|
| **Tier 1** | Every scheduled run | `loop-constraints` → `loop-budget` → `loop-triage` → `aoa repair triage` | No (L1 report-only) |
| **Tier 2** | Same run, **only if gate allows** | `fable-repair` → one fix → `loop-verifier` → draft PR | Yes (one item, worktree) |

Preflight (local or in automation prompt):

```bash
python3 -m aoa.cli repair gate                 # combined preflight
python3 -m aoa.cli repair gate --for triage    # Automation A
python3 -m aoa.cli repair gate --for repair     # Automation B
python3 -m aoa.cli repair gate --json
```

Exit codes: `0` = proceed (`triage-ok` or `l2-allowed`), `1` = skip (`skip` / `l1-only`), `2` = pause.

---

## Cursor Cloud Agent — two automations

Create **two** scheduled automations in Cursor (repo: AOA-Financial, branch: `main`).

### Automation A — Daily sense (always on)

| Setting | Value |
|---------|-------|
| **Name** | `AOA daily triage` |
| **Cadence** | Daily, 14:00 UTC (adjust to your morning) |
| **Branch** | `main` |

**Prompt:**

```text
Run loop-constraints, then loop-budget, then loop-triage on AOA-Financial.

Read STATE.md, LOOP.md, loop-constraints.md, loop-budget.md first.
Run: python3 -m aoa.cli repair gate --for triage
If gate action is "pause", update STATE.md High Priority with loop-pause-all note and exit.
If action is "skip", log to loop-run-log.md and exit (daily cap reached).

Always:
1. loop-triage → update STATE.md + append loop-run-log.md (Level L1, outcome report-only)
2. python3 -m aoa.cli repair triage → refresh queue.json

Do NOT change application code in this automation.
Do NOT open a fix PR unless a separate L2 automation runs.
Never auto-merge. Never edit .env or live trading paths.
```

### Automation B — Conditional fix (L2, after human promotion)

| Setting | Value |
|---------|-------|
| **Name** | `AOA fable repair L2` |
| **Cadence** | Daily, 15:00 UTC (1h after triage) |
| **Branch** | `main` |
| **Prerequisite** | `L2: enabled` in STATE.md (see below) |

**Prompt:**

```text
Run the fable-repair skill on AOA-Financial.
Read loop-constraints.md, docs/safety.md, LOOP.md.

Run: python3 -m aoa.cli repair gate --for repair --json
If action is not "l2-allowed", append one line to loop-run-log.md (outcome: report-only, note gate reason) and exit.

If l2-allowed:
1. aoa repair worktree --item-id <first fixable item_id from queue.json>
2. minimal-fix (maker) — ONE item only
3. loop-verifier (checker) in a NEW agent context — never self-verify
4. python3 -m ruff check src tests && python3 -m pytest -q
5. Draft PR only; never auto-merge; never push without draft PR

Respect denylist: src/aoa/risk/guards.py, .env*, profiles/live.env
Max 3 fix attempts per item; escalate in STATE.md after that.
```

---

## Enable L2 automation (human gate)

After [docs/loop-l2-checklist.md](../loop-l2-checklist.md) is complete, add to `STATE.md`:

```markdown
## Loop automation

- L2: enabled
- Enabled on: 2026-07-04 by Aaron
```

Until this section exists, `aoa repair gate` returns **`l1-only`** even when fixable items exist.

To roll back: remove the line or set `loop-pause-all` under High Priority.

---

## Gate logic (what the preflight checks)

| Check | `--for triage` | `--for repair` |
|-------|----------------|----------------|
| `loop-pause-all` | **pause** | **pause** |
| daily-triage cap (24h) | **skip** | ignored |
| L2 not enabled | ignored | **l1-only** |
| No fixable queue items | ignored | **l1-only** |
| fable-repair cap (24h) | ignored | **l1-only** |
| Else | **triage-ok** | **l2-allowed** |

Caps from `loop-budget.md`: daily-triage 2 runs / 100k tokens; fable-repair 4 runs / 200k tokens.

---

## Local cron (optional host checks)

Cursor Cloud Agent handles agent work. On a machine that stays up, use cron for **cheap deterministic checks** (no LLM):

```cron
# /etc/cron.d/aoa-loop-preflight (example — edit paths)

# Daily 13:55 UTC — refresh queue before Cloud Agent triage
55 13 * * * cd /path/to/AOA-Financial && pip install -e ".[dev]" -q && python3 -m aoa.cli repair triage >> logs/repair-triage.log 2>&1

# Daily 13:58 UTC — print gate decision for your logs
58 13 * * * cd /path/to/AOA-Financial && python3 -m aoa.cli repair gate >> logs/repair-gate.log 2>&1

# Weekdays — trading swarm (separate API budget; NOT the Fable trial)
# 0 14 * * 1-5 cd /path/to/AOA-Financial && python3 -m aoa.cli loop >> logs/aoa-loop.log 2>&1
```

Do **not** cron an unattended L2 fix without the gate and draft-PR workflow.

---

## Weekly human rhythm (Max 5×)

| Day | You (Claude Code) | Automations |
|-----|-------------------|-------------|
| Mon–Fri | Skim `STATE.md`, merge draft PRs | Tier 1 daily |
| After L2 promotion | Review one L2 PR/week min | Tier 2 when gate allows |
| Fri | Check `loop-run-log.md` token estimates | Pause if trial ending |

---

## Kill switch

1. Add to `STATE.md` → High Priority: `loop-pause-all`
2. Disable Cursor Automations A and B
3. Clear flag only after root cause fixed

---

## Quick reference — run order

```
Every day (Automation A):
  constraints → budget → repair gate → triage → repair triage → STATE + run-log

If gate = l2-allowed (Automation B):
  fable-repair → worktree → minimal-fix → loop-verifier → draft PR

Never in the same unattended run:
  trading loop + code fix + merge to main
```
