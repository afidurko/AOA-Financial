# HFT strategy reference

[afidurko/hft](https://github.com/afidurko/hft) is a fork of
[keyianpai/hft](https://github.com/keyianpai/hft): a C++ high-frequency futures
stack (CTP market data / orders, ZeroMQ IPC, waf build) with open strategy and
backtest sources. AOA Financial keeps it as an **optional sibling reference** —
same pattern as AutoHedge / FinancePy — not as a live order path.

This is **not** the optional offline L2 engine (`aoa.hftbacktest` /
[hftbacktest-integration.md](hftbacktest-integration.md)); that lane is separate.

## What AOA takes from it

| Upstream module | Idea | AOA landing |
|-----------------|------|-------------|
| `simplearb` | Pair mid-diff bands from trailing mean/std; open outside bands; exit at mean; position-asymmetric stop-loss | `calibrate_spread_bands`, `open_side_from_bands`, `hit_mean`, `stop_loss_hit` |
| `simplemaker` / `arbmaker` | Train μ±σ mid-diff thresholds; MidBuy/MidSell quoting gates; spread gate | `calibrate_maker_diffs`, `mid_buy_ok`, `mid_sell_ok`, `spread_tight_enough` |
| `strat_MA` | Short vs long MA golden / death cross (strict inequality) | `ma_cross_signal` (Julie already uses MA/RSI tooling on bars) |
| `ctpdata` / `ctporder` / proxies | Process split: data → strategy → order | Architecture inspiration only — **not** wired |

AOA stays bar-based (Alpaca / Moomoo equities & cash options). There is no tick
book, no CTP, and no microsecond path in this repo.

## Safety (Hard Floor)

- Do **not** vendor or run the C++ binaries from an AOA loop.
- Do **not** put CTP / exchange credentials in `.env`, `brain/`, or `vault/`.
- Do **not** set `AOA_ENV=live` or submit live orders from HFT code.
- Python helpers in `aoa.research.hft_patterns` never call a broker.

## Clone beside the repo

```bash
./scripts/hft-setup.sh
# or: HFT_DIR=/path/to/hft HFT_REPO=https://github.com/afidurko/hft.git ./scripts/hft-setup.sh
```

The sibling directory `hft/` is gitignored.

## Use the Python patterns

```python
from aoa.research.hft_patterns import (
    calibrate_spread_bands,
    open_side_from_bands,
    stop_loss_hit,
    calibrate_maker_diffs,
    mid_buy_ok,
    ma_cross_signal,
)

bands = calibrate_spread_bands([0.1, 0.2, -0.1, 0.0, 0.15], min_train=5, range_width=1.0)
side = open_side_from_bands(0.5, bands)  # buy / sell / flat — research signal only
stopped = stop_loss_hit(position=1, mid_diff=-1.0, bands=bands)
maker = calibrate_maker_diffs([0.1, 0.2, -0.1, 0.0, 0.15], min_train=5)
quote_ok = mid_buy_ok(10.0, 9.8, up_diff=maker.up_diff)
cross = ma_cross_signal(short_prev=9.0, long_prev=10.0, short_now=11.0, long_now=10.5)
```

## Map to Julie / study cortex

- Mesh: `brain/mesh/repos.yaml` entry `hft`
- Spine: `brain/spine/Algorithms.md`
- Curriculum: `bridge-hft-spread` (pairs bands ↔ OU mean reversion)
- Catalog: [docs/help.md](../help.md)

## Upstream layout (cheat sheet)

```
hft/src/simplearb/     statistical arb on main/hedge mids
hft/src/simplemaker/   hedged maker
hft/src/arbmaker/      arb + maker hybrid
hft/src/strat_MA/      MA crossover
hft/src/ctpdata/       CTP market data process
hft/src/ctporder/      CTP order process
hft/src/backtest/      replay / matcher
```

Build/run notes live in the upstream README (CentOS, g++, waf, ZeroMQ 4.1.2).
AOA agents should read strategies for ideas; they should not compile or deploy
that stack from a cloud loop.
