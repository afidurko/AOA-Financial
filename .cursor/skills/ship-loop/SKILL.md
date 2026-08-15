---
name: ship-loop
description: >
  Task-looping agent that discovers PR/branch issues, fixes them one at a time,
  proofreads (ruff+pytest+scope), and marks the PR ready for human merge.
  Never auto-merges. Use to wrap a feature branch until ship-ready.
user_invocable: true
---

# Ship Loop — discover → fix → proofread → ready

You are the **Ship** task-looping agent. Drive a branch/PR to **ready for human
merge**. Maker/checker split still applies for code fixes.

## Hard rules

1. Read `loop-constraints.md` first (Hard Safety Floor + Auto-12).
2. **Never auto-merge** to `main`. Ready = draft→ready-for-review + green gates.
3. Fix **one** open issue per iteration; then re-discover / proofread.
4. Max **3** attempts per issue → mark blocked and escalate.
5. Denylist unchanged: `.env*`, `profiles/live.env`, `src/aoa/risk/guards.py`.

## Meshed shortcut

```bash
python3 -m aoa.cli ship discover --pr <N>   # seed queue
python3 -m aoa.cli ship status              # open issues
# fix next issue (minimal-fix / coding-engineer)
python3 -m aoa.cli ship fixed <issue-id>
python3 -m aoa.cli ship proofread           # must pass
python3 -m aoa.cli ship ready               # only if gates pass
# then ManagePullRequest draft=false (never merge)
```

Or: `python3 -m aoa.cli tasks run ship-ready` for discover + proofread check.

## Loop algorithm

```
constraints → ship discover
while open issues:
  pick next issue
  if kind in {lint, tests, conflict, merge_base, roster, docs, custom}:
    implement minimal fix (or merge main)
    ship fixed <id>  OR  ship attempt <id> [--blocked]
  if kind == proofread:
    ship proofread  # independent checker — re-run tests yourself
ship ready → mark PR ready for review → stop (human merges)
```

## Proofread checklist (before ready)

- [ ] No conflict markers in `src/` / `tests/`
- [ ] `ruff check src tests` passes
- [ ] `pytest -q` passes
- [ ] Branch not silently diverged without merge-base issue closed
- [ ] Scope matches the PR intent (no unrelated vault/journal noise)

## Output each iteration

```markdown
## Ship loop

**Branch / PR:** …
**Next issue:** <id> — <title>
**Action:** fixed | blocked | proofread | ready
**Open remaining:** N
```

## Handoff

- Code edits → after fix, do **not** self-approve; run `aoa ship proofread`.
- Blocked roster/product decisions → document options and stop for human.
- On `ready` → update PR body, set draft=false, announce — do not merge.
