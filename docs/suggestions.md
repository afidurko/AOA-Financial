# Suggestions — after test sweep (2026-09-20)

Rebased onto current `main` (open-quant / VisualHFT / workspaces). Battery:
`ruff` `src`/`tests`, pytest **568 passed / 9 skipped**, `test_core.py` **38 OK**,
`aoa tasks run verify`, `aoa team code` (dry-run, no broker), `aoa openquant
smoke`, `aoa hftish status`, ATTL dry-run, named open-quant **trillion** stress
(3×10⁹ property checks; full 10¹² is `--iterations`).

## Done in this pass

- `aoa team code` no longer constructs a live broker (OpenD-down no longer
  blocks the required coding/fix/simplify path).
- Escalated repair items print as `[HOLD]` instead of `[FIX]`.
- Dry-run `aoa team code` does not rewrite `STATE.md`.
- Rebased onto `main`; kept help-catalog companions + suggestions link.

## Operator / env

| Suggestion | Why |
|------------|-----|
| Start OpenD or switch paper-dry to Alpaca (`upg-001`) | `[HOLD] Start Moomoo OpenD` — `aoa team health` still needs a broker; coding path does not |
| Set a real `ANTHROPIC_API_KEY` | `[HOLD]` — template key blocks LLM reasoning |
| `AOA_QM_URL=http://localhost:8081` + Node ≥ 24 + Postgres | QM companion is wired; dashboard **QM ↗** stays hidden until the URL is set |
| `aoa workspaces setup` | Mesh OpenStock / QM / VisualHFT / hftbacktest siblings |
| Install extras for skipped coverage | 9 skips: `torch`, `financepy` (×4), `hftbacktest` (×3), `tradingagents` |

## Next automatable backlog

| Id | Suggestion |
|----|------------|
| `upg-001` | Default paper profiles to Alpaca so CI/cloud `team health` works without OpenD |
| `upg-014` | Pass `brain_context` into swarm blackboard / signal adapter (Julie-only today; 7 algos meshed) |
| `upg-015` | Push Kai critical reports through BRIEF / iPhone |
| — | CI job: `aoa team code` dry-run so the required coding loop stays exercised |
| — | Optional extras job for `torch` / `financepy` / `hftbacktest` / `tradingagents` |

`upg-006` (httpx2) already landed on `main` (#91). Deprecation warnings are gone
from the default pytest run.

## Test / CI hygiene

- Keep `python -m unittest discover -s tests -p 'test_core.py'` as the
  `aoa_financial` job — discovering `-s aoa_financial` imports the package as
  tests and fails.
- `aoa team health` is a **trading** check; `aoa team code` is the **coding**
  check. Don’t wire CI to `team health` unless a broker is present.
- Named stress: `aoa openquant stress trillion` ≈ 3×10⁹ checks (~90 min here).
  Full 10¹² is `aoa openquant stress trillion --iterations 1000000000000`.

## Do not do from a loop

- Do not auto-merge, edit `.env`, or weaken `src/aoa/risk/guards.py` unless the
  user explicitly asks to merge.
- Do not treat `[HOLD]` High Priority items (OpenD, API keys) as L2 auto-fixes.
