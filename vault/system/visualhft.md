---
type: system-companion
name: visualhft
enabled: true
url_env: AOA_VISUALHFT_URL
setup: scripts/visualhft-setup.sh
docs: docs/how-to/visualhft-integration.md
repo: https://github.com/afidurko/VisualHFT
locked: []
---
# VisualHFT — microstructure workspace

Optional sibling integration. Clone with `./scripts/visualhft-setup.sh` (plus
oxyplot). Python study ports: `aoa visualhft`. Mesh status: `aoa workspaces status`.

Desktop host is Windows/.NET 10 only. AOA remains the only order path — VisualHFT
REST triggers may alert via `AOA_CUSTOM_APP_WEBHOOK_URL` but never auto-trade.
