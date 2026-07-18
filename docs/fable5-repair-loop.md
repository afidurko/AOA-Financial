# Fable 5 Repair Loop — AOA-Financial

This document describes how AOA-Financial implements **loop engineering** with a **Claude Fable 5**-style harness: autonomous discovery, maker/checker subagents, worktree isolation, and external state.

## Why Fable 5 here

Fable 5 is built for long-horizon agentic work: plan across stages, delegate to subagents, and verify in separate contexts. Loop engineering adds the control plane: schedules, skills, state files, and explicit human gates.

The critical rule (from Anthropic harness design): **the agent that implements a fix must not grade it.** Use `loop-verifier` in a fresh session after `minimal-fix`.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  fable-repair (orchestrator skill / aoa repair triage)      │
└────────────┬───────────────────────────────┬────────────────┘
             │                               │
     ┌───────▼────────┐              ┌───────▼────────┐
     │  minimal-fix   │              │ loop-verifier  │
     │  (maker)       │   ────────▶  │ (checker)      │
     │  worktree      │   new ctx    │ run pytest     │
     └────────────────┘              └────────────────┘
             │                               │
             └─────────── STATE.md ──────────┘
                         repair/queue.json
```

## CLI

| Command | Purpose |
|---------|---------|
| `aoa repair triage` | Run Bob audit + verify + STATE scan; write queue |
| `aoa repair queue` | Show queued items |
| `aoa repair worktree` | Create `.aoa-worktrees/repair-*` for isolated fix |

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `AOA_REPAIR_ENABLED` | `true` | Enable repair loop |
| `AOA_REPAIR_SYNC_STATE` | `true` | Rewrite `STATE.md` on triage |
| `AOA_REPAIR_PATH` | `data/{env}/repair` | Queue + run log |
| `AOA_REPAIR_WORKTREES_DIR` | `.aoa-worktrees` | Git worktree root |

## Relationship to other loops

- **Daily triage (`loop-triage`)** — report-only signal; feeds `STATE.md` which repair triage reads.
- **Workloop (`aoa workloop`)** — larger autonomous improvements with team review + Aaron approval.
- **Trading loop (`aoa loop`)** — market cycles; does not modify application code.

## Promotion L1 → L2

1. Week one: `loop-triage` only (no code).
2. Enable `fable-repair` with worktree + verifier for fixable audit/verify items.
3. Escalate architectural or denylist paths to human / workloop.

## Planned: ATTL (five-member proofread on coding tasks)

Today, Bob→Julie→Alan→Aaron→user team review lives on **workloop** only.
The proposed Agentic Task-Team Loop wires that proofread into the repair /
task-chain coding path, and adds user-gated task-loop creation.

See [design/agentic-task-team-loop.md](design/agentic-task-team-loop.md).
No behavior change until that design is approved and phased in.
