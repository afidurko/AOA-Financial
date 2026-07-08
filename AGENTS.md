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
python3 -m aoa.cli tasks run verify       # same checks via task loop
python3 -m aoa.cli tasks run tier1-check  # gate preflight
python3 -m aoa.cli repair triage
python3 -m aoa.cli repair gate --for triage
python3 -m aoa.cli repair gate --for repair
python3 -m aoa.cli team health
```

Full install (web dashboard + import sweep):

```bash
pip install -e ".[dev,web]"
```

Core-only install (trading CLI; `aoa.web.app` import is optional in Bob's sweep):

```bash
pip install -e ".[dev]"
```

## Loop conventions

- Report-only week one (L1) before enabling auto-fix (L2)
- See `LOOP.md` for cadence and human gates
- L2 promotion: `docs/loop-l2-checklist.md`
- Binding constraints: `loop-constraints.md` and `docs/safety.md`
- State file: `STATE.md` (commit after each triage run)
- Run log: `loop-run-log.md` (markdown table rows)

## Loop run order

```
loop-constraints → loop-budget (start) → loop-triage → STATE.md + loop-run-log.md → loop-budget (end)
```

Deterministic preflight (no LLM): `aoa tasks run tier1` · Prompt shortkeys: `aoa tasks list` · `aoa tasks show L1`

L2 (one item per run):

```
aoa repair triage → … → minimal-fix → loop-verifier → draft PR (human merge)
```

## Project skills

| Skill | Purpose |
|-------|---------|
| `loop-constraints` | Binding guardrails (runs first) |
| `loop-budget` | Token caps and run-log enforcement |
| `loop-triage` | Daily engineering triage → `STATE.md` |
| `fable-repair` | Fable 5 orchestrator — discover, delegate, verify |
| `minimal-fix` | Smallest L2+ fix for one item (maker) |
| `loop-verifier` | Maker/checker for L2+ code changes |
| `coding-engineer` | Code health, Bob/Julie audit patterns |
