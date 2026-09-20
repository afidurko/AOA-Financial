# Suggestions — after test sweep (2026-09-20)

Ran the full in-repo battery (ruff on `src`/`tests`, pytest 409 collected,
`unittest` `test_core.py`, `aoa tasks run verify`, repair triage, ATTL dry-run,
code-quality audit). Below is what is still worth doing — **not** required for
the current green suite.

## Done in this pass

- `aoa team code` no longer constructs a live broker (OpenD-down no longer
  blocks the required coding/fix/simplify path).
- Escalated repair items print as `[HOLD]` instead of `[FIX]`.
- Dry-run `aoa team code` does not rewrite `STATE.md`.

## Operator / env

| Suggestion | Why |
|------------|-----|
| Set `AOA_BROKER=alpaca` in paper profiles (`upg-001`) | `aoa team health` still needs a reachable broker; default Moomoo OpenD is down in most CI/cloud agents |
| `AOA_QM_URL=http://localhost:8081` + Node ≥ 24 + Postgres | QM companion is merged but not running; dashboard **QM ↗** stays hidden until the URL is set |
| Install extras if you need skipped coverage | 6 skips: `torch`, `financepy` (×4), `tradingagents` |
| Delete stale branch `cursor/help-related-qm-d441` | Already merged as #61 |

## Next automatable backlog

| Id | Suggestion |
|----|------------|
| `upg-006` | Still seeing FastAPI/Starlette + `websockets.legacy` deprecation warnings — add `httpx2` / filter if you want a quiet pytest |
| `upg-009` | Workloop upgrade pipeline is High Priority / human-hold (`[HOLD]`) — document UpgradeStage cadence, don’t auto-merge |
| `upg-014` | Pass `brain_context` into swarm blackboard / signal adapter (Julie-only today) |
| `upg-015` | Push Kai critical reports through BRIEF / iPhone |

## Test / CI hygiene

- Keep `python -m unittest discover -s tests -p 'test_core.py'` as the
  `aoa_financial` job — discovering `-s aoa_financial` imports the package as
  tests and fails.
- `aoa team health` is a **trading** check; `aoa team code` is the **coding**
  check. Don’t wire CI to `team health` unless a broker is present.
- Optional: add a CI job that runs `aoa team code` (dry-run) so the required
  loop path stays exercised.

## Do not do from a loop

- Do not auto-merge, edit `.env`, or weaken `src/aoa/risk/guards.py`.
- Do not treat `[HOLD]` High Priority items as L2 auto-fixes.
