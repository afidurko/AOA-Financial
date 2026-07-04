# OpenStock integration

[OpenStock](https://github.com/Open-Dev-Society/OpenStock) is an open-source market
dashboard (Next.js, Finnhub, TradingView). AOA Financial keeps it as a **sibling
clone** for research and watchlists while the swarm runs on Alpaca at
`http://localhost:8080`.

## Architecture

```
┌─────────────────────┐     shared Finnhub key (optional)
│  AOA Financial      │──────────────────────────────┐
│  aoa serve :8080    │                              │
│  (swarm + trading)  │                              ▼
└─────────────────────┘                    ┌─────────────────────┐
                                           │  OpenStock          │
                                           │  next dev :3000     │
                                           │  (charts, watchlist)│
                                           └─────────────────────┘
```

- **AOA** — autonomous trading swarm, risk guardrails, team dashboard.
- **OpenStock** — human-facing market UI; AGPL-3.0, maintained upstream.
- **Link** — set `AOA_OPENSTOCK_URL` so the AOA dashboard header opens OpenStock.

OpenStock is **not** vendored into this repo. Clone it beside the project root.

## 1. Clone OpenStock

```bash
git clone https://github.com/Open-Dev-Society/OpenStock.git
```

Or use the setup script (idempotent):

```bash
./scripts/openstock-setup.sh
```

## 2. Sync environment

Copy `openstock.env.example` to `OpenStock/.env`, or generate from your AOA `.env`:

```bash
./scripts/sync-openstock-env.sh
```

The sync script bridges:

| AOA `.env` | OpenStock `.env` |
|------------|------------------|
| `FINNHUB_API_KEY` | `NEXT_PUBLIC_FINNHUB_API_KEY` |
| (generated) | `BETTER_AUTH_SECRET` |
| (default local) | `MONGODB_URI` |

Required OpenStock keys (see upstream README): Finnhub, MongoDB, Better Auth,
Gemini + Inngest (for email workflows), Gmail (Nodemailer). For local UI-only
dev you can use placeholder values and skip Inngest.

## 3. Run locally (development)

**Terminal A — MongoDB** (Docker):

```bash
docker compose -f docker-compose.openstock.yml up -d openstock-mongodb
```

**Terminal B — OpenStock:**

```bash
cd OpenStock
npm install
npm run dev
```

**Terminal C — AOA dashboard:**

```bash
pip install -e ".[dev,web]"
cp .env.example .env   # add API keys
export AOA_OPENSTOCK_URL=http://localhost:3000
aoa serve
```

- AOA swarm: http://localhost:8080
- OpenStock UI: http://localhost:3000

## 4. Run with Docker (full stack)

Requires Docker. From the repo root:

```bash
./scripts/openstock-setup.sh
./scripts/sync-openstock-env.sh
docker compose -f docker-compose.yml -f docker-compose.openstock.yml --profile openstock up -d --build
```

Services:

| Service | Port | Profile |
|---------|------|---------|
| `web` (AOA) | 8080 | default |
| `openstock` | 3000 | `openstock` |
| `openstock-mongodb` | 27017 | `openstock` |

Set in `.env`:

```env
AOA_OPENSTOCK_URL=http://localhost:3000
OPENSTOCK_PORT=3000
```

## 5. Verify

```bash
# OpenStock unit tests (no MongoDB required)
cd OpenStock && npm test

# AOA web + integration
python3 -m pytest tests/test_web.py -q
```

## Notes

- OpenStock is AGPL-3.0. If you modify or deploy it, comply with upstream license terms.
- `aoa_financial` can use the same `FINNHUB_API_KEY` for fundamentals (`stock/metric`).
- Trading execution stays in AOA only; OpenStock does not place orders.
