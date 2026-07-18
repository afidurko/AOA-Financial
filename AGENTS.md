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
python3 -m aoa.cli team health
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
  → aoa attl run          # Nova + gate + Reed + Kai (+ worktree when allowed)
  → maker / verifier only if coding
  → draft PR (human merge)
  → loop-budget (end)
```

L1 triage still: `loop-triage` + `aoa repair triage` (report-only discovery).

## Project skills

| Skill | Purpose |
|-------|---------|
| `loop-constraints` | Hard floor + auto-12 (runs first) |
| `loop-budget` | Token caps and run-log enforcement |
| `loop-triage` | Daily engineering triage → `STATE.md` |
| `fable-repair` | Repair orchestrator meshed into ATTL |
| `minimal-fix` | Maker — smallest coding fix |
| `loop-verifier` | Checker when verifying a PR / Kai path |
| `coding-engineer` | Twelve-member code-health patterns |
