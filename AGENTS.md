# AGENTS.md — AOA-Financial

## Test commands

```bash
python3 -m ruff check src tests
python3 -m pytest -q
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

L2 (one item per run):

```
… → minimal-fix → loop-verifier → draft PR (human merge)
```

## Project skills

| Skill | Purpose |
|-------|---------|
| `loop-constraints` | Binding guardrails (runs first) |
| `loop-budget` | Token caps and run-log enforcement |
| `loop-triage` | Daily engineering triage → `STATE.md` |
| `minimal-fix` | Smallest L2+ fix for one triage item |
| `loop-verifier` | Maker/checker for L2+ code changes |
| `coding-engineer` | Code health, Bob/Julie audit patterns |
