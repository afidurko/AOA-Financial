# Safety — meshed loop and agent operations

Binding rules for unattended agent loops. Aligns with `loop-constraints.md`
(Hard Safety Floor + ATTL Auto-12 Policy).

## Hard Safety Floor

Never edit without explicit human approval:

- `.env`, `.env.*`
- `auth/`, `payments/`, `secrets/`, `credentials/`
- `profiles/live.env`
- `src/aoa/risk/guards.py` (hard risk rules)

Never:

- Auto-merge to `main` (draft PRs only)
- Live orders from loop runs (`ALPACA_LIVE=true`, `AOA_ENV=live` without `AOA_LIVE_ACK`)
- Disable or bypass risk guards
- Store secrets in `brain/` or `vault/`

## Kill switch

- `STATE.md` flag: `loop-pause-all`
- Pause Cursor Automations until a human clears it
- `aoa attl run` and repair gates respect pause

## ATTL Auto-12 (meshed)

| Concern | Behavior |
|---------|----------|
| Mode | `auto-12` by default |
| Review | Kai **critical-only** (flaw / system failure / `aoa attl report`) |
| Team | 12 members — see `aoa attl roster` / `brain/mesh/index.yaml` |
| Second brain | `brain/` meshed into vault + Julie algorithms |
| Task factory | Reed proposes from repair + backlog |
| User | Ultimate override; can fix anything after the fact |

Routine process review and “activate before use” are **not** required under auto-12.

## Fable 5 / coding path (inside ATTL)

```
aoa attl run → (automatable item) worktree → maker → tests → draft PR
```

- Maker (`minimal-fix` / Reed handoff) and checker (`loop-verifier`) stay separate **when Kai engages** or when verifying a coding fix before draft PR.
- Under auto-12, skip full team proofread unless critical.
- Fixes in `.aoa-worktrees/` when using repair worktrees.

## Workloop

- Larger discover→merge improvements
- Merge still requires `aoa workloop approve` when `AOA_WORKLOOP_ALLOW_MERGE` is set
- Shares Bob/Julie/Alan/Aaron signals; ATTL owns the coding task factory

## MCP / connectors

- Optional for daily triage
- Read-only GitHub discovery first; no write scopes until trusted

## See also

- `loop-constraints.md`
- `docs/design/agentic-task-team-loop.md`
- `docs/fable5-repair-loop.md`
- `LOOP.md`
