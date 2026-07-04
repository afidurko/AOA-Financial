# L2 promotion checklist — daily triage

Operational level **L1** (report-only) is active until every item below is satisfied and a human explicitly approves L2.

> **Note:** Loop Ready audit score (e.g. 100/100 from `npx @cobusgreyling/loop-audit`) measures **scaffold completeness**, not operational level. A repo can be scaffold-ready while still running L1.

## Prerequisites

- [ ] L1 has run at least one full week with consistent `STATE.md` and `loop-run-log.md` updates
- [ ] No open **High Priority** items in `STATE.md` that block code changes
- [ ] Human sign-off recorded (issue comment, PR note, or explicit chat approval)

## Skills and docs

- [ ] `.cursor/skills/loop-constraints/SKILL.md` present and read first every run
- [ ] `.cursor/skills/loop-budget/SKILL.md` present
- [ ] `.cursor/skills/loop-triage/SKILL.md` present
- [ ] `.cursor/skills/loop-verifier/SKILL.md` present
- [ ] `.cursor/skills/minimal-fix/SKILL.md` present
- [ ] `loop-constraints.md` and `docs/safety.md` reviewed
- [ ] `AGENTS.md` loop run order understood

## CI and local verification

- [ ] Full install green: `pip install -e ".[dev,web]"` then `python3 -m ruff check src tests` and `python3 -m pytest -q`
- [ ] Core-only install green: `pip install -e ".[dev]"` then `python3 -m pytest -q`
- [ ] `aoa_financial` unittest suite green: `python3 -m unittest discover -s tests -p 'test_core.py' -v`
- [ ] `python3 -m aoa.cli team health` reports no CRITICAL findings

## L2 dry-run (required before production automation)

- [ ] One L2 run on a **non-critical** watch item only
- [ ] Flow: `loop-constraints` → `loop-budget` → `loop-triage` → `minimal-fix` → `loop-verifier`
- [ ] `loop-verifier` returns APPROVE or ESCALATE_HUMAN (never skip verifier)
- [ ] Open **draft PR only** — human marks ready and merges
- [ ] No auto-merge to `main`
- [ ] Run logged in `loop-run-log.md` with Level `L2`

## MCP / connectors (if enabled)

- [ ] GitHub (or other) connectors scoped **read-only** for discovery
- [ ] No write scopes until L2 dry-run succeeds and human approves expanded scope

## After promotion

1. Update `STATE.md` Watch List: note L2 active and date
2. Update `LOOP.md` Active Loops table Status column if desired
3. Set Cursor Automation prompt to allow `minimal-fix` + draft PRs (still no auto-merge)
4. Keep `loop-pause-all` kill switch documented and tested

## Rollback to L1

If an L2 run causes scope creep, test failures, or constraint violations:

1. Set `loop-pause-all` in `STATE.md` High Priority
2. Pause Cursor Automations
3. Revert to report-only prompt until human clears the flag and root cause is fixed
