---
name: fable-repair
description: >
  Fable 5 repair-loop orchestrator for AOA-Financial, meshed into ATTL auto-12.
  Discovers via aoa repair triage / aoa attl run; Reed proposes; maker fixes;
  Kai reviews only on critical; loop-verifier when verifying a coding fix.
user_invocable: true
---

# Fable 5 Repair Loop — meshed with ATTL Auto-12

You orchestrate **long-horizon system repairs** inside the **12-member ATTL mesh**.

## Meshed building blocks

| Block | AOA implementation |
|-------|-------------------|
| **Constraints** | Hard Safety Floor + Auto-12 (`loop-constraints.md`) |
| **Brain** | Nova → `aoa attl brain sync` / `brain/` |
| **Automations** | `aoa attl run` or Automation B (`ATTL` / `L2` prompts) |
| **Worktrees** | Mesh creates `repair/<id>` under `.aoa-worktrees/` when l2-allowed |
| **Skills** | `fable-repair` (you), `minimal-fix` / Reed (maker), `loop-verifier` (when verifying) |
| **Critical** | **Kai** — only on critical flaw / system failure / report |
| **State** | `STATE.md`, repair queue, `brain/captures/`, `loop-run-log.md` |

## Every run (prefer meshed shortcut)

```bash
# Preferred one-shot mesh:
python3 -m aoa.cli attl run

# Or staged:
python3 -m aoa.cli repair gate --for repair --json
python3 -m aoa.cli attl brain sync
python3 -m aoa.cli repair triage
python3 -m aoa.cli attl propose
# If outcome auto-continue + worktree path printed → minimal-fix in that worktree
# loop-verifier in a NEW context before draft PR
# Draft PR only; never auto-merge
```

1. **Constraints** — hard floor; exit if pause.
2. **Mesh** — `aoa attl run` (Nova + gate + Reed + Kai).
3. If `critical-report` → stop coding; surface capture / BRIEF.
4. If `auto-continue` with worktree → maker (`minimal-fix`) on **one** selected task.
5. Verify (ruff/pytest) → draft PR → optional `aoa tasks chain advance`.

## Review policy

- **No** mandatory five-member proofread on every fix.
- Kai engages only when Bob critical / system failure / `aoa attl report`.
- Maker ≠ checker still applies when producing a coding PR.

## Denylist (hard floor)

- `src/aoa/risk/guards.py`, `.env*`, `profiles/live.env`, live trading paths

## Cursor automation prompt

```text
Run ATTL auto-12 mesh on AOA-Financial.
Read loop-constraints.md, docs/safety.md, LOOP.md.
Run: python3 -m aoa.cli attl run
If outcome is critical-report or paused, stop and report.
If auto-continue with a worktree, minimal-fix ONE item, then loop-verifier in a new context,
then draft PR only. Never auto-merge.
```
