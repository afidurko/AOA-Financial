---
name: loop-constraints
description: >
  Read loop-constraints.md at the start of every run and enforce every rule.
  This skill runs BEFORE triage or any action skill. Constraints are binding.
  Two tiers: Hard Safety Floor + ATTL Auto-12 Policy.
user_invocable: true
---

# Loop Constraints Enforcer (meshed)

You are the guardrail. Before any other work begins, you MUST:

1. Read `loop-constraints.md` from the project root.
2. Load **Hard Safety Floor** rules — never relax these.
3. Load **ATTL Auto-12 Policy** — default operating mode (critical-only review).
4. Check if `loop-pause-all` is active → exit immediately.
5. Prefer the meshed shortcut: `aoa attl run` (constraints → brain → gate → Reed → Kai).

## How to enforce

- **Hard floor** before every edit/push/merge (denylist, no live, no auto-merge, pause).
- **ATTL auto-12:** do not invent process gates (no activate-before-use, no mandatory team proofread). Kai only on critical / system failure / `aoa attl report`.
- Interactive chat with the user: announce large pushes / issue closes; otherwise auto may proceed.
- Coding path: Reed → worktree → maker; draft PR only.

## Output at start of run

```
Constraints loaded from loop-constraints.md: N rules active (hard floor + auto-12).
```

Or programmatically: `python3 -c "from aoa.constraints import load_constraints; c=load_constraints(); print(c.rule_count, c.mode, c.pause_active)"`

If no `loop-constraints.md` exists, enforce defaults from `docs/safety.md`.

## Interaction with other skills

- `fable-repair` / `minimal-fix` — run under ATTL mesh; denylist from hard floor
- `loop-verifier` — required when Kai engages or before draft PR verify
- `loop-budget` — 80% cap → report-only
- `coding-engineer` — twelve-member mesh (Nova/Reed/Kai included)
