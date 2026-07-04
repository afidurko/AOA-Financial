---
name: fable-repair
description: >
  Fable 5 repair-loop orchestrator for AOA-Financial. Discovers issues via aoa repair triage,
  delegates fixes to minimal-fix/coding-engineer (maker), and loop-verifier (checker) in
  separate subagent contexts. Never self-grade.
user_invocable: true
---

# Fable 5 Repair Loop — AOA-Financial

You orchestrate **long-horizon system repairs**, not one-off prompts. Design the loop; let subagents execute.

## Six building blocks (this repo)

| Block | AOA implementation |
|-------|-------------------|
| **Automations** | `aoa repair triage` + Cursor Cloud Agent / Automations on cadence |
| **Worktrees** | `aoa repair worktree --item-id <id>` → `.aoa-worktrees/repair-*` |
| **Skills** | `fable-repair` (you), `minimal-fix` / `coding-engineer` (maker), `loop-verifier` (checker) |
| **Connectors** | Bob code audit, `run_verify`, `STATE.md`, optional GitHub MCP (read-only first) |
| **Sub-agents** | **Maker ≠ checker** — always spawn verifier in a fresh context after a fix |
| **State** | `STATE.md`, `data/{AOA_ENV}/repair/queue.json`, `loop-run-log.md` |

## Every run (L2 repair)

1. **Constraints** — read `loop-constraints.md`; exit if `loop-pause-all`.
2. **Budget** — read `loop-budget.md` and `loop-run-log.md` (use `loop-budget` skill).
3. **Discover** — run `aoa repair triage` (updates queue + `STATE.md`).
4. **Pick one item** — highest severity fixable item only; one fix per run.
5. **Worktree** — `aoa repair worktree --item-id <id>`.
6. **Maker subagent** — invoke `minimal-fix` or `coding-engineer` with the item detail.
7. **Checker subagent** — **new session** with `loop-verifier`; default REJECT until tests pass.
8. **Log** — append row to `loop-run-log.md`; update `STATE.md` Watch/High Priority.

## Fable 5 prompting rules

- Dispatch **parallel subagents** when items are independent; never block on unrelated work.
- Use **async handoff**: maker submits proposal; verifier runs separately with full diff + test output.
- Surface progress to the user in plain language between stages (do not dump internal reasoning).
- If verifier REJECTs → max 3 attempts per item, then escalate in `STATE.md`.

## Integration with AOA loops

| Loop | When to use |
|------|-------------|
| `aoa repair triage` | Code health + verify failures (this loop) |
| `aoa workloop` | Large discover→merge improvements (Aaron approval) |
| `aoa loop` | Trading swarm cycles (never auto-fix code from trading loop) |
| `aoa team health` | Bob/Julie snapshot before trading |

## Cursor automation prompt

```text
Run the fable-repair skill on AOA-Financial.
Read LOOP.md, loop-constraints.md, and docs/safety.md first.
Run: aoa repair triage
Fix at most ONE queued item using worktree + minimal-fix, then loop-verifier in a separate pass.
Respect all human gates. Draft PR only; never auto-merge.
```

## Denylist (never auto-fix)

- `src/aoa/risk/guards.py`, `.env*`, `profiles/live.env`, live trading paths
