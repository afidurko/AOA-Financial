# AGENTS.md — AOA-Financial

## Cursor Cloud specific instructions

Cloud agents boot from [.cursor/environment.json](.cursor/environment.json),
which runs `pip install -e ".[dev,web]"` so the trading CLI, web dashboard, and
full test suite are ready without manual setup. If you add a heavyweight system
dependency, update that `install` command so future agents inherit it.

## Test commands

```bash
python3 -m ruff check src tests
python3 -m pytest -q
python3 -m aoa.cli tasks run verify
python3 -m aoa.cli tasks run tier1-check
python3 -m aoa.cli repair triage
python3 -m aoa.cli repair gate --for triage
python3 -m aoa.cli repair gate --for repair
python3 -m aoa.cli attl status
python3 -m aoa.cli attl run --dry-run
python3 -m aoa.cli ship discover
python3 -m aoa.cli ship proofread
python3 -m aoa.cli team health
python3 -m aoa.cli team code
```

Full install (web dashboard + import sweep):

```bash
pip install -e ".[dev,web]"
```

Core-only install:

```bash
pip install -e ".[dev]"
```

## Meshed loop conventions (ATTL auto-12)

- Constraints: `loop-constraints.md` — **Hard Safety Floor** + **Auto-12 Policy**
- Safety: `docs/safety.md`
- Second brain: `brain/` (Nova) meshed into vault + Julie algorithms
- Twelve-member roster: `aoa attl roster`
- Review: **critical-only** (Kai)
- State: `STATE.md` · Run log: `loop-run-log.md`
- Design: `docs/design/agentic-task-team-loop.md`

## Canonical meshed run order

```
loop-constraints → loop-budget (start)
  → aoa team code / aoa attl run   # health+triage+Nova+Reed+Kai (+ worktree)
  → maker / verifier only if coding
  → draft PR (human merge)
  → loop-budget (end)
```

Coding / fix / simplify is **loop-required** — use `aoa team code` (or `attl run`),
not ad-hoc edits outside maker/checker.

L1 triage still: `loop-triage` + `aoa repair triage` (report-only discovery).

## Project skills

| Skill | Purpose |
|-------|---------|
| `moomooapi` | Moomoo OpenAPI — quotes, klines, orders, positions, subscriptions (official OpenD Skills) |
| `install-moomoo-opend` | Install/upgrade Moomoo OpenD + `moomoo-api` SDK (official OpenD Skills) |
| `loop-constraints` | Hard floor + auto-12 (runs first) |
| `loop-budget` | Token caps and run-log enforcement |
| `loop-triage` | Daily engineering triage → `STATE.md` |
| `fable-repair` | Repair orchestrator meshed into ATTL |
| `minimal-fix` | Maker — smallest coding fix |
| `loop-verifier` | Checker when verifying a PR / Kai path |
| `coding-engineer` | Twelve-member code-health patterns |
| `ship-loop` | Discover → fix → proofread → ready (no auto-merge) |

Official Moomoo skill packs live under `.cursor/skills/{moomooapi,install-moomoo-opend}/` and are mirrored in `.claude/skills/` for Claude Code. Source: [opend-skills.zip](https://openapi.moomoo.com/skills/opend-skills.zip). Prefer `/moomooapi` (or natural language about quotes/orders); use `/install-moomoo-opend` to install OpenD on a local machine.

## Multi-root workspaces

Companion vault/skills stack (Obsidian + Spine + Moomoo):

```bash
./scripts/knowledge-stack-setup.sh
./scripts/write-aoa-workspace.sh   # → AOA.code-workspace
```

See [docs/how-to/workspace-mesh.md](docs/how-to/workspace-mesh.md). Mesh map: `brain/mesh/repos.yaml`.
