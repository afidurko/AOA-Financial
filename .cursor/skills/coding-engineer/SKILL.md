---
name: coding-engineer
description: Maintain and simplify the AOA Financial codebase. Use when refactoring, fixing lint errors, deduplicating logic, or preventing regressions in the trading swarm.
---

# Coding Engineer — twelve-member mesh

Code health is a **team responsibility**. The meshed roster:

| Member | Coding-engineer job |
|--------|---------------------|
| **Bob** | Deterministic systems health + code integrity |
| **Julie** | Algorithm validation + clarity; reads brain mesh context |
| **Alan** | Decision aggregation + code oversight |
| **Reed** | Task-loop architect / implementer (ATTL factory + maker handoff) |
| **Kai** | Critical-only sentinel (not routine review) |
| **Nova** | Second-brain mesh curator (`brain/`) |
| **Aaron** | CEO remediate / escalate critical Kai reports |
| **Alex** | User priorities / BRIEF |

Tom / Morgan / Hailey / Andrea own market/risk lanes; they feed Alan.

## Deterministic checks (`src/aoa/team/code_engineering.py`)

Bob and Julie share `run_code_quality_audit()`:

- Shared helpers live in one module (`execution/pricing`, `brokerage/constants`)
- Web app uses `app.state`, not module singletons
- Pipeline uses `CycleContext.portfolio_output` and exposes `run_from()`
- Optional `ruff check src tests` when ruff is installed
- Import sweep for core modules

## Where things belong

| Concern | Module |
|---------|--------|
| Order limit pricing | `src/aoa/execution/pricing.py` |
| Alpaca feed/adjustment constants | `src/aoa/brokerage/constants.py` |
| Code audit | `src/aoa/team/code_engineering.py` |
| ATTL mesh | `src/aoa/attl/mesh.py` |
| Constraints loader | `src/aoa/constraints.py` |
| Second brain | `src/aoa/brain/` + `brain/` |
| Hard risk rules | `src/aoa/risk/guards.py` (deterministic, binding) |

## CLI

```bash
python3 -m aoa.cli team health
python3 -m aoa.cli attl status
python3 -m aoa.cli attl run --dry-run
python3 -m aoa.cli run
```

## Verification

```bash
python3 -m ruff check src tests
python3 -m pytest -q
```

Both must pass before opening a PR.
