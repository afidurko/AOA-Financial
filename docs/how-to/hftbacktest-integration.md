# HFT backtest (hftbacktest) integration

AOA Financial wraps [afidurko/hftbacktest](https://github.com/afidurko/hftbacktest)
(fork of [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest)) as an
**optional offline** tick-level L2/L3 backtest lane, and vendors
[afidurko/HFT-Orderbook](https://github.com/afidurko/HFT-Orderbook) as a
standalone limit-order-book for local add/cancel/execute research.

It does **not** replace:

- `aoa simulate` / `aoa.simulation` — bar Monte-Carlo and scenario stress
- `aoa_financial` walk-forward backtest — daily decision harness
- live paper/live execution — never submit orders from this path

## Install

```bash
pip install -e ".[hftbacktest]"   # tick engine (optional)
# Orderbook is vendored — no extra install required
```

PyPI wheels are used for hftbacktest. Tracked forks:

- `https://github.com/afidurko/hftbacktest`
- `https://github.com/afidurko/HFT-Orderbook`

## Commands

```bash
aoa hft status
aoa hft smoke
aoa hft smoke --events 500 --steps 30 --seed 1 --json
aoa hft book-smoke
aoa hft book-smoke --json
aoa hft run path/to/feed.npz --tick-size 0.01 --lot-size 0.001
```

`status` reports both lanes. `smoke` verifies the optional hftbacktest Numba
engine with a synthetic depth tape. `book-smoke` exercises the vendored LOB
(add/update/cancel). `run` probes an on-disk hftbacktest feed.

## Library API

```python
from aoa.hftbacktest import HAS_HFTBACKTEST, probe_status, run_npz_smoke
from aoa.orderbook import LimitOrderBook, Order, run_book_smoke

print(probe_status())
print(run_book_smoke().to_dict())

book = LimitOrderBook()
book.process(Order(uid=1, is_bid=True, size=5, price=99.0))
book.process(Order(uid=2, is_bid=False, size=5, price=101.0))
print(book.top_level)

if HAS_HFTBACKTEST:
    print(run_npz_smoke(n_events=200, steps=10).to_dict())
```

## Live trading note

Neither lane places live or paper orders. For exchange live MM, use the
hftbacktest Rust `connector` (Binance/Bybit) as a sibling process; use
`aoa.orderbook` only for local book state / research. See the cloud-agent
discussion on live setup — do not wire through `Executor` without an
explicit depth-feed design and `AOA_LIVE_ACK`.

## Safety

- Offline research only (`offline_only: true` in status JSON)
- Not wired into `Executor`, swarm stages, or `AOA_ENV=live`
- Hard safety floor still applies: no live order submission from loops
- Vendored LOB license: MIT (Nils Diefenbach / Crypto-toolbox); see
  `src/aoa/orderbook/vendor/LICENSE`

## Workspace mesh

All offline HFT/LOB lanes: [microstructure-lanes.md](microstructure-lanes.md) · `aoa microstructure status`.
