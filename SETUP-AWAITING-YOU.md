# Setup — log into Moomoo, run one command

AOA defaults to **Moomoo** + a **local Ollama** model (no cloud API keys).

## Quick start (any platform)

1. **Install Moomoo OpenD** from [moomoo.com/download/OpenAPI](https://www.moomoo.com/download/OpenAPI/)

| Platform | OpenD install |
|----------|---------------|
| macOS | `bash scripts/install_moomoo_opend_macos.sh` |
| Linux | `bash scripts/install_moomoo_opend_linux.sh` |
| Docker (unofficial) | `docker-compose.moomoo-opend.example.yml` |

Full guide: [docs/how-to/moomoo-setup.md](docs/how-to/moomoo-setup.md)

2. **Log in** with your Moomoo account (OpenD must stay running on this machine)

3. **Install Python deps** (once):

```bash
pip install -e ".[dev,web,openai]"
```

4. **Start the swarm** (auto-activates — waits for OpenD, starts Ollama):

```bash
aoa loop
# or: aoa serve
```

Optional explicit verify first: `aoa activate` (same checks + full `doctor`).

Paper dry-run by default — no orders submitted until you change `AOA_ENV`.

For **Alpaca** instead: set `AOA_BROKER=alpaca`, run `pip install -e ".[alpaca]"`, then `bash scripts/setup_alpaca_auth.sh`.

---

## What `activate` turns on

| System | How |
|--------|-----|
| **Broker** | Moomoo OpenD at `127.0.0.1:11111` (waits until you log in) |
| **Reasoning** | Local Ollama (`llama3.1`) — no Anthropic/OpenAI key |
| **Trading mode** | `paper-dry` — analyze and journal only |
| **Verify** | Full `aoa doctor` (broker + LLM ping) |

Profile: `profiles/moomoo.env` (auto-selected by `activate`). For simulate orders via OpenD, use `AOA_PROFILE=moomoo-paper` instead.

---

## Optional — cloud LLM instead of Ollama

Edit `.env`:

```bash
AOA_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Optional — Alpaca instead of Moomoo

Set `AOA_BROKER=alpaca`, run `pip install -e ".[alpaca]"`, then `bash scripts/setup_alpaca_auth.sh`.

---

## Live trading (later)

Only when you intentionally move to real money:

```bash
AOA_ENV=live
AOA_LIVE_ACK=I_UNDERSTAND
MOOMOO_LIVE=true
MOOMOO_UNLOCK_PASSWORD=your-trading-password
```

---

## If something fails

| Symptom | Fix |
|---------|-----|
| `Connect fail` / OpenD unreachable | Start OpenD; log in; check `MOOMOO_OPEND_HOST` / `MOOMOO_OPEND_PORT` |
| Ollama not running | `ollama pull llama3.1 && ollama serve` — or use Anthropic (above) |
| `unlock_trade` error | Set `MOOMOO_UNLOCK_PASSWORD` for live accounts |
| Empty bars / no data | Log into OpenD; confirm US market data subscription |

---

## Security

- Never commit `.env` (already gitignored)
- Regenerate keys if you pasted secrets in chat or Slack
- `MOOMOO_UNLOCK_PASSWORD` is sensitive — treat like a trading PIN
- Stay on `paper-dry` until you deliberately move to live trading
