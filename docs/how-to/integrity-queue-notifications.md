# How-to: Integrity queue notifications

Push alerts when Integrity Ten queues a corrective action for your approve/reject.

## Quick setup (ntfy)

1. Install [ntfy](https://ntfy.sh) on your iPhone.
2. Subscribe to a **private** topic (long random name, e.g. `aoa-integrity-yourname-x7k2`).
3. In `.env` (local only — never commit):

```bash
AOA_NTFY_TOPIC=aoa-integrity-yourname-x7k2
AOA_NTFY_SERVER=https://ntfy.sh
AOA_INTEGRITY_NOTIFY_QUEUE=true
```

4. Verify:

```bash
aoa integrity status
aoa integrity queue --push
```

`status` should show `Notify: configured via ntfy`.

## Other channels

| Channel | Env vars |
|---------|----------|
| Pushover | `AOA_PUSHOVER_USER_KEY` + `AOA_PUSHOVER_APP_TOKEN` |
| Custom app | Real `AOA_CUSTOM_APP_WEBHOOK_URL` (placeholder `example.com` URLs are ignored) |

## Commands

```bash
aoa integrity run                 # check; notify on new proposal
aoa integrity queue               # list pending
aoa integrity queue --push        # digest push for pending queue
aoa integrity attention           # Needs Attention feed (dashboard + Cursor)
aoa integrity attention --cursor  # MCP external_action payload for Cursor Cloud
aoa integrity approve <id>        # implant
aoa integrity reject <id>         # decline
```

## Cursor Needs Attention

Cloud agents surface pending integrity work in Cursor’s **Needs Attention** tab:

1. `aoa integrity attention --cursor` → JSON with `actions` (`external_action` items)
2. Call MCP `cursor-cloud` / `request-environment-setup-actions` with that `actions` array
3. User approves/rejects from Needs Attention, or runs the printed CLI commands
4. Dashboard: **Needs Attention** tab + `/api/needs-attention`

Payload is also written to `data/{env}/integrity/cursor_needs_attention.json` whenever a proposal is queued.

Hard floor: notifications never auto-merge; implant waits on your approve.
