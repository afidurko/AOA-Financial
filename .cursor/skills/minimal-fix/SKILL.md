---
name: minimal-fix
description: >
  Implement the smallest correct fix for one triage or repair item. Respects denylist paths,
  runs tests, and hands off to loop-verifier. L2+ only.
user_invocable: true
---

# Minimal Fix Skill (maker)

You are the **implementer** in a maker/checker split. Apply the smallest change that addresses **one** item. Never implement and verify in the same role.

## When to use

- Operational level **L2+** only (see `docs/loop-l2-checklist.md`)
- One item from `STATE.md` High Priority or `aoa repair queue`
- `loop-constraints` and `loop-budget` allow the run

## Before editing

1. Read `loop-constraints.md` — denylist paths are binding.
2. Run `aoa repair worktree --item-id <id>` for isolated fixes (or manual branch in `.aoa-worktrees/`).
3. Baseline tests:

```bash
python3 -m ruff check src tests
python3 -m pytest -q
```

## Implementation rules

- **One fix per run** — no drive-by refactors
- **Minimal diff** — match surrounding conventions
- **Never** edit denylist paths (see `docs/safety.md`)
- Max **3 attempts** per item; escalate after

## After editing

1. Re-run tests (same commands as above).
2. Summarize for `loop-verifier` in a **separate session**.
3. **Do not** merge — verifier and human gate follow.

## Output

```markdown
## Minimal fix summary

**Target:** <item id + title>
**Files:** <list>
**Tests:** <command + pass/fail>
**Ready for verifier:** yes
```

## Handoff

Invoke `loop-verifier` with summary and diff. Accept REJECT and iterate (up to 3 times) or ESCALATE_HUMAN.
