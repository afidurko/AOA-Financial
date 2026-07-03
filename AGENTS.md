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
- Binding constraints: `loop-constraints.md` and `docs/safety.md`
- State file: `STATE.md` (commit after each triage run)
- Run log: `loop-run-log.md` (markdown table rows)

## Project skills

| Skill | Purpose |
|-------|---------|
| `coding-engineer` | Code health, Bob/Julie audit patterns |
| `loop-triage` | Daily engineering triage |
| `loop-budget` | Token caps and run-log enforcement |
| `loop-constraints` | Binding guardrails (runs first) |
| `loop-verifier` | Maker/checker for L2+ code changes |
