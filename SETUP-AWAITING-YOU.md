# Setup — waiting on you

AOA is configured for **paper-dry** mode (safe: no real orders). Complete the items below in order. Each step needs you — nothing here can be done automatically.

Run the helper anytime:

```bash
bash scripts/setup_alpaca_auth.sh
```

---

## Step 1 — Anthropic API key (agents need this to think)

- [ ] Open [console.anthropic.com](https://console.anthropic.com/) → **API Keys** → create a key
- [ ] Edit `.env` in the project root:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
```

---

## Step 2 — Alpaca paper login (market data + paper trading)

Pick **one** method.

### Option A — Browser OAuth (recommended; matches Alpaca CLI)

- [ ] Install Alpaca CLI (if needed):

```bash
go install github.com/alpacahq/cli/cmd/alpaca@latest
export PATH="$HOME/go/bin:$PATH"
```

- [ ] Log in (opens browser — **you sign in and approve**):

```bash
alpaca profile login
```

- [ ] Confirm it worked:

```bash
alpaca doctor
alpaca account get
```

AOA reads `~/.config/alpaca/profiles/paper.yaml` automatically. **Do not paste OAuth tokens into chat.**

### Option B — API keys from Alpaca dashboard

- [ ] Go to [app.alpaca.markets](https://app.alpaca.markets) → toggle **Paper** (yellow) → **API Keys** → **Generate New Key**
- [ ] Copy **Key ID** (`PK...`) and **Secret** (shown once)
- [ ] Either run:

```bash
alpaca profile login --api-key --key PK... --secret YOUR_SECRET
```

- [ ] Or put them in `.env`:

```bash
ALPACA_API_KEY_ID=PK...
ALPACA_API_SECRET_KEY=your-secret-here
```

Keep `ALPACA_LIVE=false`.

---

## Step 3 — Verify everything

- [ ] Run:

```bash
pip install -e ".[dev]"
python3 -m aoa.cli doctor
```

You should see:

- `✓ Alpaca auth: cli-oauth (profile paper)` **or** `✓ Alpaca auth: env`
- `✓ Broker reachable (alpaca-paper); equity $...`

---

## Step 4 — First dry run (optional)

- [ ] Single safe cycle (paper-dry = no orders submitted):

```bash
python3 -m aoa.cli run
```

---

## If something fails

| Symptom | Fix |
|---------|-----|
| `401 unauthorized` | Re-run `alpaca profile login` or regenerate API keys in Alpaca dashboard |
| `ANTHROPIC_API_KEY is not set` | Complete Step 1 |
| `Alpaca credentials missing` | Complete Step 2 |
| Keys you pasted earlier failed | Those were invalid — use OAuth or fresh `PK...` keys from the dashboard |

---

## Security

- Never commit `.env` (already gitignored)
- Regenerate Alpaca keys if you pasted secrets in chat or Slack
- Stay on `AOA_ENV=paper-dry` until you deliberately move to live trading
