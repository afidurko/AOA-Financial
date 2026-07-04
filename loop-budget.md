# Loop Budget — AOA-Financial

> Primary loop: **Daily Triage** (scaffolded from [afidurko/loop-engineering](https://github.com/afidurko/loop-engineering))

## Daily limits

| Loop | Max runs/day | Max tokens/day | Max sub-agent spawns/run |
|------|--------------|----------------|--------------------------|
| Daily Triage (Cursor) | 2 | 100k | 0 (L1) / 2 (L2) |
| Trading swarm (`aoa loop`) | per market hours | broker/API bounded | N/A |
| Work loop (`aoa workloop loop`) | per `AOA_WORKLOOP_INTERVAL_SECONDS` | LLM bounded | 0 until approved |

## On budget exceed

1. Pause Cursor Automations / cloud agent schedules
2. Append event to `loop-run-log.md`
3. Set `loop-pause-all` in `STATE.md` High Priority

## Kill switch

- GitHub label or issue: `loop-pause-all`
- Resume only after human clears the flag in `STATE.md` and this Alerts section

## Alerts This Period

_(none)_

## Estimate spend

```bash
npx @cobusgreyling/loop-cost --pattern daily-triage --level L1
```
