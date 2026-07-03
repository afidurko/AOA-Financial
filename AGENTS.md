# AGENTS.md — AOA-Financial

## Test commands

```bash
python3 -m ruff check src tests
python3 -m pytest -q
```

Full install (includes web import sweep):

```bash
pip install -e ".[dev,web]"
```

## Loop conventions

- Report-only week one (L1) before enabling auto-fix (L2)
- See `LOOP.md` for cadence and human gates
- Binding constraints: `loop-constraints.md`
- State file: `STATE.md` (commit after each triage run)

## Project skills

- `coding-engineer` — code health, Bob/Julie audit patterns
- `loop-triage` — daily engineering triage (loop-engineering)
- `loop-verifier` — maker/checker for L2+ code changes
