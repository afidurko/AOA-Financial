# Loop State — AOA-Financial

Last run: 2026-07-05 00:30 UTC (Moomoo migration Phase 1 started)

## High Priority (loop is acting or waiting on human)

- **Moomoo migration Phase 1** — `AOA_BROKER=moomoo` adapter merged pending PR; **you** run OpenD locally → `docs/how-to/setup-moomoo.md` → `aoa doctor` → dry run → approve REAL

## Watch List

- **OpenD required** — Moomoo is not cloud API keys; OpenD must run on the machine that executes `aoa run`
- **Phase 2 gaps** — options chain, bracket stops, news feed (see `docs/plans/moomoo-migration-fable5.md`)
- **Rotate exposed secrets** — Alpaca/Anthropic keys pasted in chat should be regenerated

## Loop automation

- L2: disabled
- Broker migration tracked under Fable 5 plan: `docs/plans/moomoo-migration-fable5.md`

## Next actions (by owner)

| When | Owner | Task |
|------|-------|------|
| Now | **You** | Install OpenD + `pip install -e ".[dev,moomoo]"` + `export AOA_PROFILE=moomoo-paper` |
| Now | **You** | `python3 -m aoa.cli doctor` (OpenD must be running) |
| Before REAL | **You** | `AOA_DRY_RUN=true` cycle, review journal, then set `MOOMOO_TRD_ENV=REAL` + `AOA_LIVE_ACK` |
| Ongoing | **Fable trial** | Phase 2 items via `fable-repair` after Phase 1 PR merges |

## Repair queue

Machine-readable queue: `data/{AOA_ENV}/repair/queue.json`

---
Run log: loop-run-log.md
