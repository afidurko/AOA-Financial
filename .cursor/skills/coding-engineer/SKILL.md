---
name: coding-engineer
description: Maintain and simplify the AOA Financial codebase. Use when refactoring, fixing lint errors, deduplicating logic, or preventing regressions in the trading swarm.
---

# Coding Engineer — Julie, Alan, and Bob

Code health is a **team responsibility**, not a separate role. The five-member team
coordinates coding-engineer work like this:

| Member | Coding-engineer job |
|--------|---------------------|
| **Bob** | Deterministic systems health + code integrity (`BobAgent.audit_codebase`, `team.bob.code_quality` journal events) |
| **Julie** | Algorithm validation **and** code-clarity review — she reads Bob's audit and notes issues in her method notes (`team.julie.code_audit`) |
| **Alan** | Decision aggregation **and** code oversight — lowers confidence when code quality is degraded or critical |

Tom handles trend reads; Aaron (CEO) remediates recoverable issues and escalates.

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
| Code audit implementation | `src/aoa/team/code_engineering.py` |
| Bob's health gate | `src/aoa/team/bob.py` |
| Julie's clarity review | `src/aoa/team/julie.py` |
| Alan's brief + code confidence | `src/aoa/team/alan.py` |
| Pipeline stages | `src/aoa/swarm/stages.py` |
| LLM failures | Catch `LLMError`, not bare `Exception` |
| Hard risk rules | `src/aoa/risk/guards.py` (deterministic, binding) |

## CLI

```bash
python3 -m aoa.cli team health   # Bob's health + code audit
python3 -m aoa.cli team brief    # Tom→Julie→Alan with code context
python3 -m aoa.cli run           # Full team-coordinated cycle
```

## Verification checklist

```bash
python3 -m ruff check src tests
python3 -m pytest -q
```

Both must pass before opening a PR.
