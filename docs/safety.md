# Safety — loop and agent operations

Binding rules for unattended agent loops (see also `loop-constraints.md`).

## Denylist paths

Never edit without explicit human approval:

- `.env`, `.env.*`
- `auth/`, `payments/`, `secrets/`, `credentials/`
- `profiles/live.env`
- `src/aoa/risk/guards.py` (hard risk rules)

## Auto-merge policy

- **Never** auto-merge to `main`.
- Draft PRs only until a human marks ready and merges.
- Workloop merge requires Aaron approval (`aoa workloop approve`).

## Trading safety

- No live orders from loop runs (`ALPACA_LIVE=true`, `AOA_ENV=live`).
- No disabling or bypassing risk guards.
- `AOA_LIVE_ACK=I_UNDERSTAND` required for live env (human-only).

## MCP / connectors

MCP is optional for daily triage. When enabled:

- Read-only GitHub discovery first; no write scopes until L2+ is trusted.
- Scope connectors to the minimum needed for the active pattern.

## Kill switch

- GitHub label or `STATE.md` flag: `loop-pause-all`
- Pause Cursor Automations and report-only until cleared by a human.
