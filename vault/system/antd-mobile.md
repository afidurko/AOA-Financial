---
type: system-companion
name: ant-design-mobile
enabled: true
url_env: AOA_ANTD_MOBILE_URL
setup: scripts/antd-mobile-setup.sh
docs: docs/how-to/antd-mobile-integration.md
repo: https://github.com/afidurko/ant-design-mobile
locked: []
---
# ant-design-mobile — phone UI kit

Optional sibling UI kit. `aoa serve` always exposes the built-in phone shell at
`/m`. When `AOA_ANTD_MOBILE_URL` is set, the desktop header shows **UI kit ↗**.
Clone with `./scripts/antd-mobile-setup.sh`. AOA remains the only order path.
