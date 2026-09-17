# Ant Design Mobile integration

[afidurko/ant-design-mobile](https://github.com/afidurko/ant-design-mobile)
is a fork of
[ant-design/ant-design-mobile](https://github.com/ant-design/ant-design-mobile):
essential React UI blocks for mobile web apps (CSS variables, gestures, small
bundle).

AOA Financial keeps it as an **optional sibling UI kit** and ships a built-in
phone shell at `/m` that loads published `antd-mobile` against the same REST
API as the desktop dashboard. It does **not** place live orders.

## Architecture

```
┌─────────────────────┐     same REST API
│  AOA Financial      │◀──────────────────┐
│  aoa serve :8080    │                   │
│  /  desktop HTML    │                   │
│  /m antd-mobile UI  │───────────────────┘
└─────────────────────┘
          │ AOA_ANTD_MOBILE_URL (optional)
          ▼
┌─────────────────────┐
│  ant-design-mobile  │  sibling clone / fork docs
│  (component source) │
└─────────────────────┘
```

- **AOA** — brokerage, risk guardrails, trading swarm, REST API.
- **`/m`** — Vite-built mobile shell (NavBar / TabBar / Lists) for phone + Tailscale.
- **Sibling fork** — customize themes or components; not required to open `/m`.

## Install sibling (optional)

```bash
./scripts/antd-mobile-setup.sh
# or: ANTD_MOBILE_DIR=/path/to/sibling ANTD_MOBILE_REPO=https://github.com/afidurko/ant-design-mobile.git ./scripts/antd-mobile-setup.sh
```

The directory `ant-design-mobile/` is gitignored.

## Rebuild the phone shell (developers)

Source lives in `web-mobile/` (React + antd-mobile + Vite). Built assets are
committed under `src/aoa/web/static/mobile/` so `aoa serve` works without Node:

```bash
cd web-mobile
npm ci
npm run build   # → src/aoa/web/static/mobile/
```

## Run the mobile shell

```bash
pip install -e ".[dev,web]"
aoa serve
# Phone / Tailscale: http://<host>:8080/m
# Desktop: http://localhost:8080/  (header link → Mobile)
```

Optional header shortcut to the fork or component docs:

```bash
# AOA_ANTD_MOBILE_URL=https://github.com/afidurko/ant-design-mobile
```

## Mesh status

```bash
aoa workspaces status
aoa workspaces status --json
```

`antd-mobile` shows **present** when the sibling clone exists and **linked** when
`AOA_ANTD_MOBILE_URL` is set. The `/m` route is always available from `aoa serve`
when the static build is present.

## Safety (Hard Floor)

- Do **not** vendor the full component monorepo into AOA.
- Do **not** auto-submit live orders from mobile UI actions (`/m` only calls the
  same paper-safe API endpoints as the desktop dashboard).
- Do **not** put API keys in the sibling fork or dashboard HTML.
- Hard safety floor still applies (`docs/safety.md`).

## Upstream

- Docs: [https://mobile.ant.design](https://mobile.ant.design)
- Install kit: `npm install antd-mobile` (or yarn / pnpm / bun)
- AOA `/m` serves a Vite-built bundle of published `antd-mobile` (no CDN at
  runtime). Rebuild with `cd web-mobile && npm run build` after UI changes.
