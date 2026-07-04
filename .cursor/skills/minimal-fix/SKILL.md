---
name: minimal-fix
description: >
  Implement the smallest correct fix for one triage item. Respects denylist paths,
  runs tests, and hands off to loop-verifier. L2+ only.
user_invocable: true
---

# Minimal Fix Skill

You are the **implementer** in a maker/checker split. Apply the smallest change that addresses **one** triage item. Never implement and verify in the same role.

## When to use

- Operational level **L2+** only (see `docs/loop-l2-checklist.md`)
- A single item from `STATE.md` High Priority or Watch List with an explicit `next:` action
- `loop-constraints` and `loop-budget` allow the run (not paused, under token cap)

## Before editing

1. Read `loop-constraints.md` — denylist paths are binding.
2. Confirm the target issue from `STATE.md` (one item only).
3. Run baseline tests:

```bash
python3 -m ruff check src tests
python3 -m pytest -q
```

## Implementation rules

- **One fix per run** — no drive-by refactors or unrelated cleanups
- **Minimal diff** — match surrounding code style and conventions
- **Never** edit: `.env`, `.env.*`, `auth/`, `payments/`, `secrets/`, `credentials/`, `profiles/live.env`, `src/aoa/risk/guards.py`
- **Never** disable tests, skip assertions, or weaken risk guards to make CI green
- **Never** set `ALPACA_LIVE=true` or `AOA_ENV=live`
- Max **3 attempts** per item; escalate to human after the third failure

## After editing

1. Re-run tests:

```bash
python3 -m ruff check src tests
python3 -m pytest -q
```

2. Summarize for `loop-verifier`:
   - Target issue (from STATE.md)
   - Files changed and why
   - Test command + result
   - Residual risk (if any)

3. **Do not** mark the PR ready or merge — verifier and human gate follow.

## Handoff

Invoke `loop-verifier` with your summary and diff. Accept REJECT and iterate (up to 3 times) or ESCALATE_HUMAN.

## Output

```markdown
## Minimal fix summary

**Target:** <STATE.md item title>
**Files:** <list>
**Tests:** <command + pass/fail>
**Ready for verifier:** yes
```
