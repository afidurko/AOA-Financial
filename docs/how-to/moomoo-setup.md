# Moomoo broker setup

AOA defaults to **Moomoo** (`AOA_BROKER=moomoo`). Stock quotes and orders flow through **OpenD**, a local gateway that must run on the same machine as AOA.

## Quick start

```bash
pip install -e ".[dev,web,openai]"    # includes moomoo-api + OpenAI SDK for Ollama
cp .env.example .env                  # paper-dry: Ollama, no cloud API key
aoa setup moomoo                      # guided checks
```

With OpenD running:

```bash
aoa doctor
aoa run                         # paper-dry: no orders submitted
```

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
```

## 3. Verify connectivity

```bash
aoa doctor --offline   # config only (~instant)
aoa doctor             # full check; fails fast in ~3s if OpenD is down
```

Expected when healthy:

```
✓ Broker: moomoo
✓ Moomoo OpenD target: 127.0.0.1:11111 (US, simulate)
✓ Broker reachable (moomoo-paper); equity $...
✓ LLM reachable (model=...)
```

## 4. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `OpenD unreachable` | Start OpenD; check host/port |
| `moomoo-api is not installed` | `pip install -e ".[dev]"` |
| Doctor hangs (old builds) | Upgrade to build with TCP probe (`AOA_MOOMOO_CONNECT_TIMEOUT`) |
| No stock bars | Log into OpenD; confirm US market data subscription |
| Cloud / CI environment | OpenD must run locally — use Alpaca for headless: `AOA_BROKER=alpaca` |

## 5. Live trading (later)

```bash
AOA_ENV=live
AOA_LIVE_ACK=I_UNDERSTAND
MOOMOO_LIVE=true
MOOMOO_UNLOCK_PASSWORD=your-trading-password
```

See [SETUP-AWAITING-YOU.md](../../SETUP-AWAITING-YOU.md) for the full human checklist.
