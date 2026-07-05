# Moomoo migration — Fable 5 program plan

Replace Alpaca with **Moomoo OpenAPI + OpenD** for the user's **actual brokerage account**, while keeping the swarm's `Broker` abstraction and deterministic risk guards.

**Human authority:** You have final say on merges, live trading, and L2 automation. Risk guardrails in `src/aoa/risk/guards.py` remain binding for real money.

## Architecture

```
OpenD (local) ← moomoo-api SDK ← MoomooBroker(Broker ABC) ← swarm / executor
```

Alpaca code stays for rollback (`AOA_BROKER=alpaca`). Default broker is selected via `AOA_BROKER`.

## Fable 5 team roles

| Agent | Phase 1 (this PR) | Phase 2 | Phase 3 |
|-------|-------------------|---------|---------|
| **Bob** | `MoomooBroker`, config, `build_broker`, doctor | bars batch, constants cleanup | remove Alpaca-only paths in CLI |
| **Julie** | tests, docs, symbol mapping clarity | refactor duplicate timeframe maps | README rewrite |
| **Tom** | quotes, daily bars, market open | multi-TF bars via OpenD | scanner / most-actives |
| **Alan** | orchestration unchanged (Broker ABC) | news fallback (Finnhub) | dashboard broker label |
| **Aaron (you)** | approve OpenD setup, first dry run | enable REAL + `AOA_LIVE_ACK` | merge + production cadence |

## Maker / checker workflow

Each phase = one Fable repair item:

```
aoa repair worktree → minimal-fix (maker) → loop-verifier (checker) → draft PR
```

Prompt shortkey: `aoa tasks show MOOMOO-P1` (when added to `loop-prompts.yaml` on main).

## Phases

### Phase 1 — Broker adapter (in progress)

- [x] `MoomooBroker` implementing `Broker`
- [x] `AOA_BROKER=moomoo` config + profiles
- [x] `build_broker` factory + doctor OpenD check
- [x] `docs/how-to/setup-moomoo.md`
- [ ] User: OpenD running + doctor green on your machine

### Phase 2 — Parity

- [ ] Options chain + orders (Moomoo US options)
- [ ] Multi-timeframe bar batch (`AlpacaBarsFetcher` equivalent)
- [ ] Protective bracket behavior or documented alternative
- [ ] News via Finnhub / Moomoo

### Phase 3 — Deprecate Alpaca default

- [ ] README + `.env.example` Moomoo-first
- [ ] CI with mocked Moomoo only
- [ ] Optional: keep Alpaca as `AOA_BROKER=alpaca` for contributors

## Rollback

Set `AOA_BROKER=alpaca` and restore Alpaca keys — no swarm code changes required.

## Links

- [setup-moomoo.md](../how-to/setup-moomoo.md)
- [Moomoo OpenAPI docs](https://openapi.moomoo.com/moomoo-api-doc/en/)
