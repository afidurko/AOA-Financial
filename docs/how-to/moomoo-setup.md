# Moomoo broker setup

AOA defaults to **Moomoo** (`AOA_BROKER=moomoo`) plus a **local WASTE LLM**
(not Claude). Stock quotes and orders flow through **OpenD**; agent reasoning
hits WASTE on `:8000`.

## Quick start

```bash
pip install -e ".[dev,web]"    # includes moomoo-api
cp .env.example .env           # Moomoo + WASTE defaults
aoa setup moomoo               # guided OpenD checks (+ OpenD skills)
```

Agent skills (official OpenD pack, vendored under `.cursor/skills/`):

| Skill | Use when |
|-------|----------|
| `/moomooapi` | Quotes, klines, news, orders, positions via OpenD scripts |
| `/install-moomoo-opend` | Download/install OpenD + upgrade `moomoo-api` |

AOA runtime wires the same OpenAPI surface into `MoomooBroker` and `MoomooNewsFeed`
(`get_search_news`, `OrderType.MARKET` / `STOP`, `average_cost` / `unrealized_pl`,
`get_top_movers_rank`).

With OpenD running (and WASTE on `:8000`):

```bash
aoa doctor
aoa run                        # paper-dry: no orders submitted
```

WASTE serve: [waste-local-llm.md](waste-local-llm.md).

## 1. Install OpenD

| Platform | Method |
|----------|--------|
| **macOS** | `bash scripts/install_moomoo_opend_macos.sh` — downloads GUI OpenD |
| **Linux (Ubuntu/CentOS)** | [Command-line OpenD](https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html) or `bash scripts/install_moomoo_opend_linux.sh` |
| **Docker (unofficial)** | See `docker-compose.moomoo-opend.example.yml` — community image, not Moomoo-official |

After install:

1. Launch OpenD and log in with your Moomoo account
2. Confirm it listens on `127.0.0.1:11111` (default)

## 2. Environment profiles

| Profile | File | Mode |
|---------|------|------|
| Paper dry-run (default) | `profiles/paper-dry.env` | Moomoo + `AOA_DRY_RUN=true` |
| Moomoo paper simulate | `profiles/moomoo-paper.env` | Real simulate orders via OpenD |
| Alpaca paper (optional) | set `AOA_BROKER=alpaca` | See `scripts/setup_alpaca_auth.sh` |

```bash
export AOA_PROFILE=paper-dry      # or moomoo-paper
```

Key `.env` variables:

```bash
AOA_BROKER=moomoo
MOOMOO_OPEND_HOST=127.0.0.1
MOOMOO_OPEND_PORT=11111
MOOMOO_LIVE=false                 # simulate unless AOA_ENV=live
MOOMOO_UNLOCK_PASSWORD=           # required only for live trading

# Local LLM (default — not Claude)
AOA_LLM_PROVIDER=openai_compatible
AOA_LLM_BASE_URL=http://127.0.0.1:8000/v1
AOA_MODEL=kimi-linear
```

## 3. Verify connectivity

```bash
aoa doctor --offline   # config only (~instant)
aoa doctor             # OpenD + bars + WASTE; fails fast ~3s if OpenD is down
```

Expected when healthy:

```
✓ Broker: moomoo
✓ Moomoo OpenD target: 127.0.0.1:11111 (US, simulate)
✓ Broker reachable (moomoo-paper); equity $...
✓ LLM client initialized (provider=openai_compatible, base_url=http://127.0.0.1:8000/v1)
✓ LLM reachable (model=kimi-linear)
```

`aoa doctor` does **not** require Alpaca keys when `AOA_BROKER=moomoo`.

## 4. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `OpenD unreachable` / broker check failed | Start OpenD; check host/port |
| `moomoo-api is not installed` | `pip install -e ".[dev]"` |
| Doctor hangs (old builds) | Upgrade to build with TCP probe (`AOA_MOOMOO_CONNECT_TIMEOUT`) |
| No stock bars | Log into OpenD; confirm US market data subscription |
| LLM check failed | Start WASTE: `python3 -m serve MODEL --port 8000` |
| Cloud / CI environment | OpenD must run locally — use Alpaca for headless: `AOA_BROKER=alpaca` |

## 5. Live trading (later)

```bash
AOA_ENV=live
AOA_LIVE_ACK=I_UNDERSTAND
MOOMOO_LIVE=true
MOOMOO_UNLOCK_PASSWORD=your-trading-password
```

See [SETUP-AWAITING-YOU.md](../../SETUP-AWAITING-YOU.md) for the full human checklist.
