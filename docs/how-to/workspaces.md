# Companion workspaces mesh

> Trading companions (`aoa workspaces`) — OpenStock, QM, VisualHFT, hftbacktest,
> ant-design-mobile.
> For the Obsidian/Spine/Cursor multi-root vault mesh, see [workspace-mesh.md](workspace-mesh.md).

AOA Financial stays the brokerage/risk authority. Optional **sibling workspaces**
plug in for research UI, agent harnesses, and microstructure tooling. None of
them place live orders.

```
┌──────────────────┐   AOA_OPENSTOCK_URL    ┌────────────┐
│  AOA Financial   │───────────────────────▶│ OpenStock  │
│  aoa serve :8080 │   AOA_QM_URL           │ charts UI  │
│  /m phone shell  │───────────────────────▶│ QM harness │
│  aoa visualhft   │   AOA_VISUALHFT_URL    │ VisualHFT  │
│  aoa workspaces  │───────────────────────▶│ desktop L2 │
│                  │   AOA_ANTD_MOBILE_URL  │ antd-mobile│
│                  │   optional extra       │ hftbacktest│
└──────────────────┘───────────────────────▶└────────────┘
```

## Status

```bash
aoa workspaces status
aoa workspaces status --json
```

Shows whether each companion is **linked** (env URL / install) and **present**
(local clone path).

## Setup shortcuts

| Workspace | Setup | Env | Docs |
|-----------|-------|-----|------|
| OpenStock | `./scripts/openstock-setup.sh` | `AOA_OPENSTOCK_URL` | [openstock-integration.md](openstock-integration.md) |
| QM | `./scripts/qm-setup.sh` | `AOA_QM_URL` | [qm-integration.md](qm-integration.md) |
| VisualHFT | `./scripts/visualhft-setup.sh` | `AOA_VISUALHFT_URL` | [visualhft-integration.md](visualhft-integration.md) |
| hftbacktest | `pip install -e ".[hftbacktest]"` (orderbook vendored) | (optional package) | [hftbacktest-integration.md](hftbacktest-integration.md) |
| ant-design-mobile | `./scripts/antd-mobile-setup.sh` | `AOA_ANTD_MOBILE_URL` | [antd-mobile-integration.md](antd-mobile-integration.md) |

One-shot (all companions that have setup scripts):

```bash
aoa workspaces setup
# or: ./scripts/workspaces-setup-all.sh
```

The HFT workspace is **linked** when the vendored orderbook is healthy and/or
the optional `hftbacktest` extra is installed. `aoa hft`, `aoa visualhft`, and
`aoa workspaces` are offline — they do not create `.env` or load brokerage config.

VisualHFT Positions/Orders empty: [visualhft-positions-orders.md](visualhft-positions-orders.md).

Phone UI (`/m`) is always served by `aoa serve` — see [antd-mobile-integration.md](antd-mobile-integration.md).

## Dashboard

When the corresponding `AOA_*_URL` is set, `aoa serve` exposes header shortcuts
(OpenStock ↗, QM ↗, VisualHFT ↗, UI kit ↗) via `/api/config`. The desktop header
always links to **Mobile** (`/m`).

## Safety

- Mesh commands are status/link only — they never submit broker orders
- VisualHFT REST triggers may POST alerts to `AOA_CUSTOM_APP_WEBHOOK_URL`; AOA
  does not auto-execute trades from those alerts
- Hard safety floor still applies (`docs/safety.md`)
