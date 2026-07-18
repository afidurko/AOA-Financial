# Loop Constraints

> Add rules below with `/constraints <rule>` in your agent.
> The `loop-constraints` skill reads this file at the start of every run.
> Constraints here are **binding** — the agent MUST follow them.

## Push & Merge
- Don't push before telling me
- Never auto-merge to main without human approval
- Always create a draft PR first; let me review before marking ready

## Paths
- Never edit .env, .env.*, auth/, payments/, secrets/, credentials/
- Never edit infrastructure configs without human approval
- Never edit `profiles/live.env` or enable `AOA_ENV=live` without explicit human approval

## Trading (AOA-specific)
- Never submit live orders or set `ALPACA_LIVE=true` in a loop run
- Never disable risk guards in `src/aoa/risk/guards.py`
- Workloop merge (`AOA_WORKLOOP_ALLOW_MERGE=true`) requires Aaron approval every run

## Code
- Always run tests before proposing a fix
- Never disable tests to make CI green
- Never refactor unrelated code — one fix per run
- Max 3 fix attempts per item; escalate after

## L2 autonomy scope
- L2 auto-fix is enabled ONLY for auto-fixable code-health items (code audit, ruff, verify failures)
- Never auto-fix an item that needs CEO (Aaron) approval, higher escalation, or a manual user notification — leave it in STATE.md High Priority for a human
- Items touching secrets, `.env`, credentials, live trading, payments, or denylist paths always require escalation (never auto-fixed)
- The repair gate marks these `requires_escalation` and excludes them from the L2-actionable set

## ATTL (auto-12) — user-supervised
- ATTL defaults to `auto-12` with **critical-only** review (Kai). Routine process review is not required — user interacts directly and can fix.
- Hard safety floor still applies: never edit `.env*`, secrets, `profiles/live.env`, or disable `src/aoa/risk/guards.py`; never auto-merge to main; honor `loop-pause-all`.
- Force a report anytime with `aoa attl report`.

## Communication
- Always tell me what you're about to do before doing it
- Never close an issue or PR without my approval

## Budget
- If token spend hits 80% of daily cap, switch to report-only
- If loop-pause-all is active, exit immediately

---
<!-- Add your own rules below. Use plain English. The loop reads this verbatim. -->
