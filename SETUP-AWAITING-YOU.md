# Setup — waiting on you

AOA defaults to **Moomoo** (`AOA_BROKER=moomoo`). Complete the steps below in order.

Run the helper anytime:

```bash
bash scripts/setup_moomoo_auth.sh
python3 scripts/moomoo_setup_stage.py a   # Stage A checklist (beginner walkthrough)
```

**Visual step-by-step:** [docs/how-to/moomoo-setup-walkthrough.md](docs/how-to/moomoo-setup-walkthrough.md)

For **Alpaca** instead: set `AOA_BROKER=alpaca`, run `pip install -e ".[alpaca]"`, then `bash scripts/setup_alpaca_auth.sh`.

---

## Step 1 — Anthropic API key (agents need this to think)

- [ ] Open [console.anthropic.com](https://console.anthropic.com/) → **API Keys** → create a key
- [ ] Edit `.env` in the project root:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
```

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
- `✓ LLM reachable (model=...)`

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
| `ANTHROPIC_API_KEY is not set` | Complete Step 1 |
| `Alpaca credentials missing` | Complete optional Alpaca section or switch back to Moomoo |

---

## Security

- Never commit `.env` (already gitignored)
- Regenerate keys if you pasted secrets in chat or Slack
- `MOOMOO_UNLOCK_PASSWORD` is sensitive — treat like a trading PIN
- Stay on `AOA_ENV=paper-dry` until you deliberately move to live trading
