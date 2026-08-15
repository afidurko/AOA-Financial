---
type: system-companion
name: qm
enabled: true
url_env: AOA_QM_URL
setup: scripts/qm-setup.sh
docs: docs/how-to/qm-integration.md
repo: https://github.com/afidurko/qm
locked: []
---
# QM — multiplayer agent harness

Optional sibling integration. When `AOA_QM_URL` is set, the AOA dashboard header
and `/api/config` expose a link to the QM web surface. Clone with
`./scripts/qm-setup.sh`. AOA remains the only order path.
