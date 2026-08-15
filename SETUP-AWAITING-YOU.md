# Setup — waiting on you

AOA defaults to **Moomoo** (`AOA_BROKER=moomoo`) and a **local WASTE LLM**
(not Claude). Complete the steps below in order.

**macOS automated bootstrap** (fixes Python 3.9 → 3.12, venv, `pip install`):

```bash
cd ~/AOA-Financial
bash scripts/setup_mac.sh --moomoo
```

Then start a local WASTE serve (Step 1) before `aoa doctor`.

Manual helper:

```bash
aoa setup moomoo
# or: bash scripts/setup_moomoo_auth.sh
```

| Platform | OpenD install |
|----------|---------------|
| macOS | `bash scripts/install_moomoo_opend_macos.sh` |
| Linux | `bash scripts/install_moomoo_opend_linux.sh` |
| Docker (unofficial) | `docker-compose.moomoo-opend.example.yml` |

Full guide: [docs/how-to/moomoo-setup.md](docs/how-to/moomoo-setup.md)

For **Alpaca** instead: set `AOA_BROKER=alpaca`, run `pip install -e ".[alpaca]"`, then `bash scripts/setup_alpaca_auth.sh`.

---

## Step 1 — Local WASTE LLM (agents need this to think)

AOA does **not** use Claude by default. Point agents at a local
[WASTE](https://github.com/sqliteai/waste) OpenAI-compatible server:

- [ ] Build/serve WASTE (see [docs/how-to/waste-local-llm.md](docs/how-to/waste-local-llm.md))
- [ ] Confirm `.env` has (already in `.env.example`):

```bash
AOA_LLM_PROVIDER=openai_compatible
AOA_LLM_BASE_URL=http://127.0.0.1:8000/v1
AOA_LLM_API_KEY=local
AOA_MODEL=kimi-linear
```

- [ ] `curl` the server’s `/v1/chat/completions` once before running AOA

Claude is opt-in only: `AOA_LLM_PROVIDER=anthropic` + `pip install 'aoa-financial[anthropic]'`.

---

## Step 2 — Moomoo OpenD (default broker)

OpenD must run on the **same machine** as AOA.

- [ ] Download **Moomoo OpenD** from [moomoo.com/download/OpenAPI](https://www.moomoo.com/download/OpenAPI/)
- [ ] Install, launch, and log in with your **Moomoo account**
- [ ] Confirm it listens on `127.0.0.1:11111` (default)

---

## Step 3 — Install Python deps

```bash
pip install -e ".[dev,web]"
```

(`moomoo-api` is included by default; add `[alpaca]` only if using Alpaca.)

---

## Step 4 — Verify

With OpenD running:

```bash
python3 -m aoa.cli doctor
```

You should see:

- `✓ Broker: moomoo`
- `✓ Moomoo OpenD target: 127.0.0.1:11111 (US, simulate)`
- `✓ Broker reachable (moomoo-paper); equity $...`
- `✓ LLM client initialized (provider=openai_compatible, …)`
- `✓ LLM reachable (model=kimi-linear)`

---

## Step 5 — First dry run

```bash
python3 -m aoa.cli run
```

`AOA_ENV=paper-dry` keeps orders from being submitted even when the broker connects.

---

## Optional — Alpaca paper instead of Moomoo

1. Set in `.env`: `AOA_BROKER=alpaca`
2. Run: `pip install -e ".[alpaca]"`
3. Either `alpaca profile login` **or** set `ALPACA_API_KEY_ID` + `ALPACA_API_SECRET_KEY` (`PK...` keys)
4. Keep `ALPACA_LIVE=false`

See `bash scripts/setup_alpaca_auth.sh` for the full Alpaca checklist.

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
| `Connect fail` / OpenD unreachable | Start OpenD; check `MOOMOO_OPEND_HOST` / `MOOMOO_OPEND_PORT` |
| `unlock_trade` error | Set `MOOMOO_UNLOCK_PASSWORD` for live accounts |
| Empty bars / no data | Log into OpenD; confirm US market data subscription |
| `401 unauthorized` (Alpaca) | Re-run `alpaca profile login` or regenerate API keys |
| `ANTHROPIC_API_KEY is not set` | Only if you opted into Claude — or switch back to `AOA_LLM_PROVIDER=openai_compatible` |
| `AOA_LLM_BASE_URL` / LLM check failed | Start WASTE serve on port 8000 — [waste-local-llm.md](docs/how-to/waste-local-llm.md) |
| `Alpaca credentials missing` | Complete optional Alpaca section or switch back to Moomoo |

---

## Security

- Never commit `.env` (already gitignored)
- Regenerate keys if you pasted secrets in chat or Slack
- `MOOMOO_UNLOCK_PASSWORD` is sensitive — treat like a trading PIN
- Stay on `AOA_ENV=paper-dry` until you deliberately move to live trading
