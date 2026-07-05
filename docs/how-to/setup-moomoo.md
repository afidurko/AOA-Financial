# Setup — Moomoo OpenAPI (OpenD)

AOA uses **Moomoo OpenAPI** through a locally running **OpenD** gateway — not cloud API keys like Alpaca.

## Prerequisites

1. Moomoo account with **OpenAPI** enabled ([Moomoo OpenAPI](https://www.moomoo.com/OpenAPI))
2. **OpenD** installed and running on the same machine as AOA (default `127.0.0.1:11111`)
3. Python extra: `pip install -e ".[dev,moomoo]"`

## Quick start (paper / simulate)

```bash
export AOA_PROFILE=moomoo-paper
# or set in .env:
#   AOA_BROKER=moomoo
#   MOOMOO_TRD_ENV=SIMULATE

python3 -m aoa.cli doctor
python3 -m aoa.cli run          # respects AOA_DRY_RUN
```

## Live (your real Moomoo account)

**You have final say on every trade.** AOA still applies deterministic risk guards in `src/aoa/risk/guards.py`.

1. Start OpenD and **unlock trading** in the OpenD UI (required for `MOOMOO_TRD_ENV=REAL`)
2. Copy `profiles/moomoo-live.env.example` → `.env` and set:
   - `AOA_ENV=live`
   - `AOA_LIVE_ACK=I_UNDERSTAND`
   - `MOOMOO_TRD_ENV=REAL`
   - `MOOMOO_ACCOUNT_ID=` (if you have multiple accounts)
3. Run `python3 -m aoa.cli doctor` — must show OpenD reachable + equity
4. First cycle: `AOA_DRY_RUN=true python3 -m aoa.cli run` (plan only)
5. When ready: `AOA_DRY_RUN=false python3 -m aoa.cli run`

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AOA_BROKER` | `alpaca` | Set to `moomoo` |
| `MOOMOO_OPEND_HOST` | `127.0.0.1` | OpenD host |
| `MOOMOO_OPEND_PORT` | `11111` | OpenD port |
| `MOOMOO_TRD_ENV` | `SIMULATE` | `SIMULATE` (paper) or `REAL` (live) |
| `MOOMOO_SECURITY_FIRM` | `FUTUINC` | US Moomoo firm |
| `MOOMOO_ACCOUNT_ID` | `0` | Optional account id |
| `MOOMOO_MARKET` | `US` | Quote/trade market prefix |

## Limitations (phase 1 adapter)

- US equities: quotes, bars, orders
- **Options chain / options orders**: not wired yet (returns empty chain)
- **Bracket/OTO protective stops**: not wired — plain market/limit only
- **News feed**: disabled when `AOA_BROKER=moomoo` (use Finnhub or add Moomoo news later)

See [docs/plans/moomoo-migration-fable5.md](../plans/moomoo-migration-fable5.md) for the full migration plan.
