# Fable 5 trial vs Claude Max 5× — operating schedule

Use **two Claude surfaces** for AOA-Financial: a **time-boxed Fable 5 trial** (Cursor Cloud Agent + loop harness) and your **Claude Max 5× subscription** (interactive Claude Code). They do **not** replace the **Anthropic API key** required to run the trading swarm.

## What each surface is

| Surface | What it is | Pays for | Powers `aoa run` / `aoa loop`? |
|---------|------------|----------|--------------------------------|
| **Fable 5 trial** | Cursor Cloud Agent running loop skills (`loop-triage`, `fable-repair`) with caps in `loop-budget.md` | Trial / automation credits (bounded) | No |
| **Claude Max 5×** | claude.ai + Claude Code in your terminal/IDE ($100/mo, ~5× Pro usage) | Flat subscription | No |
| **Anthropic API** | `ANTHROPIC_API_KEY` in `.env` — programmatic Messages API | Pay-as-you-go tokens | **Yes** |

**Rule:** Max 5× and Fable trial cover **engineering loops** (triage, fixes, setup, review). The **swarm’s agent reasoning at runtime** always bills the API key, regardless of subscription.

**Claude Code gotcha:** If `ANTHROPIC_API_KEY` is exported in the same shell as Claude Code, Claude Code bills the **API**, not Max 5×. Use separate terminals: `.env` sourced only for `aoa` commands.

---

## Task routing (who does what)

### Fable 5 trial — autonomous, bounded

Best for repeatable loop work with maker/checker and draft PRs only.

| Task | Skill / command | Level |
|------|-----------------|-------|
| Daily signal scan | `loop-triage` | L1 report-only |
| Code-health discovery | `aoa repair triage` | L2 discover |
| One minimal fix + verifier | `fable-repair` → `minimal-fix` → `loop-verifier` | L2 (one item/run) |
| STATE + run log | Update `STATE.md`, `loop-run-log.md` | Every run |
| Draft PR | Cloud agent branch + draft PR | Never auto-merge |

**Do not use Fable trial for:** filling `.env` secrets, Alpaca OAuth in browser, live trading, workloop merge, or burning API tokens on market cycles.

**Daily caps** (`loop-budget.md`):

| Loop | Max runs/day | Max tokens/day |
|------|--------------|----------------|
| Daily triage | 2 | 100k |
| Fable 5 repair | 4 | 200k |

At **80%** of cap → report-only. At **100%** or `loop-pause-all` → stop.

### Claude Max 5× — interactive, human-paced

Best for setup, judgment calls, and long debugging sessions.

| Task | How |
|------|-----|
| First-time setup | `SETUP-AWAITING-YOU.md`: API key, `alpaca profile login`, `aoa doctor` |
| Review draft PRs | Mark ready, merge after human approval |
| Deep refactors / design | Claude Code + gstack (`/review`, `/investigate`, `/ship`) |
| Workloop approvals | `aoa workloop approve` (Aaron gate) |
| L2 promotion sign-off | `docs/loop-l2-checklist.md` |

**Do not use Max 5× for:** unattended 24/7 trading loops (use API + `aoa loop` on a host you control).

### Anthropic API — runtime only

| Task | When |
|------|------|
| `aoa run` / `aoa loop` / web auto-loop | After paper-dry verified |
| `aoa_financial analyze` (live analyst) | Optional research |

Tune cost in `.env`: `AOA_MODEL`, `AOA_EFFORT`, `AOA_TRADING_AGENTS_ENABLED`, universe size.

---

## Schedule by timeframe

### Every day (automated — Fable trial)

See [loop-automation-schedule.md](loop-automation-schedule.md) for Cursor prompts, cron, and `aoa repair gate`.

```
loop-constraints → loop-budget → repair gate → loop-triage → repair triage → STATE.md + loop-run-log.md
```

- **Duration:** ~5–15 min agent time, &lt;100k tokens (L1).
- **Outcome:** report-only unless a fixable repair item exists.

If repair queue has a **fixable** item and budget allows:

```
fable-repair → aoa repair triage → worktree → minimal-fix → loop-verifier → draft PR
```

- **Duration:** ~30–90 min, ≤200k tokens, **one fix max**.
- **Human gate:** review draft PR (Max 5× session optional).

### Week 1 (setup — Max 5× + you)

| Day | Owner | Action |
|-----|-------|--------|
| 1 | Max 5× | Complete `SETUP-AWAITING-YOU.md`; `pip install -e ".[dev]"`; `aoa doctor` green |
| 1 | Max 5× | First `aoa run` in `paper-dry` |
| 2–7 | Fable trial | Daily L1 triage only (no L2 until checklist + human sign-off) |
| 7 | Max 5× | Review `loop-run-log.md`; decide L2 promotion |

### Ongoing (steady state)

| Cadence | Owner | Action |
|---------|-------|--------|
| Daily | Fable trial | L1 triage (+ L2 repair if fixable & budget OK) |
| Weekly | Max 5× | Merge queued PRs, retro, tune `.env` |
| Market hours | API + host | `aoa loop` or dashboard (`AOA_WEB_AUTO_LOOP`) — **separate API budget** |
| On alert | Max 5× | `loop-pause-all` response, incident review |

### When Fable trial ends

1. Pause Cursor Automations (`loop-budget.md` kill switch).
2. Keep daily triage manual via Max 5× + `loop-triage` skill.
3. L2 repair remains available manually; re-enable Cloud Agent when trial renews or paid.

---

## Execution checklist (start of any run)

1. Read `loop-constraints.md` — exit if `loop-pause-all`.
2. Read `loop-budget.md` + last 24h of `loop-run-log.md`.
3. Route task to Fable trial vs Max 5× vs API per table above.
4. Append one row to `loop-run-log.md` when done.
