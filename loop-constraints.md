# Loop Constraints — AOA-Financial (meshed)

> Source of truth for agents. Loaded by the `loop-constraints` skill **before** any other work.
> Two tiers only: **Hard Safety Floor** (always) and **ATTL Auto-12 Policy** (default operating mode).

## Hard Safety Floor (never relax)

These apply to every loop, skill, and agent — including ATTL auto-12:

1. Honor `loop-pause-all` in `STATE.md` — exit immediately
2. Never edit `.env`, `.env.*`, `auth/`, `payments/`, `secrets/`, `credentials/`
3. Never edit `profiles/live.env` or enable `AOA_ENV=live` without explicit human approval
4. Never disable or weaken `src/aoa/risk/guards.py`
5. Never submit live orders or set `ALPACA_LIVE=true` from a loop run
6. Never auto-merge to `main` — draft PRs only until the user merges
7. Never disable tests to make CI green
8. Never store API keys or secrets in `brain/`, `vault/`, or captures

## ATTL Auto-12 Policy (default)

Meshed control plane: **brain/** + **12-member team** + **repair/task factory** + **algorithms**.

| Setting | Value |
|---------|--------|
| Mode | `auto-12` (`aoa attl status`) |
| Roster | Tom · Julie · Morgan · Hailey · Alan · Andrea · Bob · Aaron · Alex · **Nova** · **Reed** · **Kai** |
| Review | **Critical-only** (Kai) — critical flaw, system failure, or `aoa attl report` |
| Process gates | Relaxed — user interacts directly and can fix; no mandatory pre-ask / activate step |
| Knowledge | Nova syncs `brain/`; Julie/algorithms read `brain_context_for_algorithms()` |
| Task creation | Reed auto-proposes from repair queue + upgrade backlog (need-ordered) |
| Coding path | Reed → worktree → maker; checker only when Kai engages or verify fails critically |

### What auto-12 may do without asking

- Run `aoa attl run` / propose / brain sync
- Create repair worktrees for automatable items
- Open **draft** PRs
- Advance the task chain after a completed automatable item
- Capture run notes under `brain/captures/`

### What still stops the loop

- Hard Safety Floor violations
- Gate action `pause` (`loop-pause-all`)
- Kai critical report (`outcome: critical-report`) — notify user via BRIEF/capture; do not keep patching blindly
- Items touching denylist / secrets / live → leave in High Priority (never auto-fix)

### Interactive sessions (Cursor chat with the user)

- Prefer announcing intent before large pushes or closing issues/PRs
- User can override any auto decision; prefer their instruction over ATTL defaults

## Trading & workloop

- Trading swarm (`aoa loop`) never modifies application code
- Workloop merge still requires `aoa workloop approve` when merge is enabled
- Infrastructure config edits outside ATTL coding tasks need human approval

## Budget

- If token spend hits 80% of daily cap → report-only (no new coding side effects)
- Caps: `loop-budget.md` (include `attl` / `fable-repair` rows)

## Canonical run order (meshed)

```
loop-constraints → loop-budget (start)
  → aoa attl brain sync          # Nova
  → aoa repair triage            # discover
  → aoa attl run                 # Reed + critical Kai gate
  → (if coding) maker → tests → draft PR
  → brain capture + loop-run-log → loop-budget (end)
```

Shortcut: `aoa attl run` performs the meshed auto cycle (pause/gate/brain/propose/critical).

## Docs

- Design: `docs/design/agentic-task-team-loop.md`
- Safety detail: `docs/safety.md`
- Brain rules: `brain/_CLAUDE.md`
- Mesh graph: `brain/mesh/index.yaml`
