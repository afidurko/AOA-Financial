# Companion workspaces mesh

AOA Financial stays the brokerage/risk authority. Optional **sibling workspaces**
plug in for research UI, agent harnesses, and microstructure tooling. None of
them place live orders.

```
┌──────────────────┐   AOA_OPENSTOCK_URL    ┌────────────┐
│  AOA Financial   │───────────────────────▶│ OpenStock  │
│  aoa serve :8080 │   AOA_QM_URL           │ charts UI  │
│                  │───────────────────────▶│ QM harness │
│  aoa visualhft   │   AOA_VISUALHFT_URL    │ VisualHFT  │
│  aoa workspaces  │───────────────────────▶│ desktop L2 │
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
| hftbacktest | `pip install -e ".[hftbacktest]"` | (optional package) | [hftbacktest-integration.md](hftbacktest-integration.md) |

`hftbacktest-integration.md` ships with the optional HFT PR/extra; until then
`aoa workspaces status` still reports install presence.

## Dashboard

When the corresponding `AOA_*_URL` is set, `aoa serve` exposes header shortcuts
(OpenStock ↗, QM ↗, VisualHFT ↗) via `/api/config`.

## Safety

- Mesh commands are status/link only — they never submit broker orders
- VisualHFT REST triggers may POST alerts to `AOA_CUSTOM_APP_WEBHOOK_URL`; AOA
  does not auto-execute trades from those alerts
- Hard safety floor still applies (`docs/safety.md`)
