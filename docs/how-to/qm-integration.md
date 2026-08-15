# QM integration

[QM](https://github.com/afidurko/qm) is a multiplayer agent harness (Slack + web)
from [yc-software/qm](https://github.com/yc-software/qm). AOA Financial keeps it
as an **optional sibling** for collaborative agent work around the trading swarm —
scoped memory, crons, sandbox, and harness-agnostic loops — while AOA stays the
brokerage and risk authority.

## Architecture

```
┌─────────────────────┐         AOA_QM_URL (header link)
│  AOA Financial      │────────────────────────────────┐
│  aoa serve :8080    │                                │
│  (swarm + trading)  │                                ▼
└─────────────────────┘                      ┌─────────────────────┐
                                             │  QM                 │
                                             │  core HTTP :8081    │
                                             │  (Slack + web UI)   │
                                             └─────────────────────┘
```

- **AOA** — autonomous trading swarm, cash-account guardrails, team dashboard.
- **QM** — multiplayer agent harness; not vendored; not used to place orders.
- **Link** — set `AOA_QM_URL` so the AOA dashboard header opens QM.

QM’s own `.env` defaults `PORT=8080`, which collides with AOA’s web port. The
setup script writes `PORT=8081` for the sibling clone.

## 1. Clone QM

```bash
./scripts/qm-setup.sh
```

Override clone location / upstream:

```bash
QM_DIR=/path/to/qm QM_REPO=https://github.com/yc-software/qm.git ./scripts/qm-setup.sh
```

## 2. Configure AOA

In AOA `.env`:

```bash
AOA_QM_URL=http://localhost:8081
```

Then:

```bash
aoa serve
# or: python3 -m aoa.cli doctor   # prints QM harness link when set
```

Open **http://localhost:8080/** — the header shows **QM ↗** when `AOA_QM_URL` is set.

## 3. Run QM (operator-owned)

QM is a full Node/Postgres deployment, not a single `npm run dev` demo. After
clone:

1. Follow upstream [getting started](https://github.com/afidurko/qm/blob/main/docs/getting-started.md)
   / `qm init` for org deploy layers (Fly or AWS).
2. Or use QM’s `npm run dev-instance` / local docs once Postgres and secrets are ready.
3. Point `AOA_QM_URL` at the live web/portal URL (local or deployed).

AOA does **not** start, proxy, or authenticate to QM — it only surfaces the URL
in `/api/config` and the dashboard header (same pattern as OpenStock).

## Env reference

| Variable | Where | Purpose |
|----------|--------|---------|
| `AOA_QM_URL` | AOA `.env` | Dashboard + `/api/config` link |
| `QM_DIR` | setup script | Sibling path (default `./qm`) |
| `QM_REPO` | setup script | Git URL (default `afidurko/qm`) |
| `QM_PORT` | setup script | Written into sibling `.env` as `PORT` (default `8081`) |

## Safety

- Trading execution stays in AOA only; QM does not place broker orders.
- Keep QM’s security posture and secrets in the QM deployment — never commit them here.
- See also [docs/help.md](../help.md) and [docs/safety.md](../safety.md).
