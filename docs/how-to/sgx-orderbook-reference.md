# SGX full order-book strategy reference

[afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy](https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy)
is a fork of
[rorysroes/SGX-Full-OrderBook-Tick-Data-Trading-Strategy](https://github.com/rorysroes/SGX-Full-OrderBook-Tick-Data-Trading-Strategy):
Jupyter notebooks that feature-engineer SGX A50 full limit-order-book ticks
(rise ratio, weighted depth) and train classical ML classifiers
(RandomForest / ExtraTrees / AdaBoost / GradientBoosting / SVM) to predict
near-horizon tradeability and sketch P&amp;L.

AOA Financial keeps it as an **optional sibling reference** — same pattern as
`hft` / `example-hftish` / VisualHFT — not as a live order path.

## What AOA takes from it

| Upstream notebook | Idea | AOA landing |
|-------------------|------|-------------|
| `Feature_Selection/*Rise*` | Ask/bid **rise ratio** over a trailing time window | `rise_ratio`, `rise_pressure_side` |
| `Feature_Selection/*Depth*` | Weighted multi-level **depth** ask/bid ratios | `weighted_depth`, `depth_from_snapshot`, `depth_pressure_side` |
| Label builders | Forward window: bid lifts if bid &gt; min(ask) | `forward_tradeable`, `label_forward_tradeable` |
| `Model_Selection` | Rolling sklearn model selection + P&amp;L sketch | Stay in the sibling notebooks — **not** ported |

AOA stays bar-based (Alpaca / Moomoo equities &amp; cash options). There is no SGX
A50 feed, no microsecond L2 history store, and no HFT execution path in this
repo. Combine with the optional `aoa.orderbook` / `aoa hft` lanes when those
land for offline L2 experiments.

## Safety (Hard Floor)

- Do **not** vendor or auto-run the sibling notebooks from an AOA loop.
- Do **not** put exchange credentials in `.env`, `brain/`, or `vault/`.
- Do **not** set `AOA_ENV=live` or submit live orders from SGX research code.
- Python helpers in `aoa.research.sgx_orderbook_patterns` never call a broker.

## Clone beside the repo

```bash
./scripts/sgx-orderbook-setup.sh
# or: SGX_DIR=/path/to/sibling SGX_REPO=https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy.git ./scripts/sgx-orderbook-setup.sh
```

The sibling directory `SGX-Full-OrderBook-Tick-Data-Trading-Strategy/` is
gitignored.

## Use the Python patterns

```python
from aoa.research.sgx_orderbook_patterns import (
    BookLevel,
    BookSnapshot,
    combine_pressure,
    depth_from_snapshot,
    depth_pressure_side,
    feature_vector,
    rise_pressure_side,
    rise_ratio,
)

book = BookSnapshot(
    bids=(BookLevel(99.0, 40.0), BookLevel(98.0, 20.0), BookLevel(97.0, 10.0)),
    asks=(BookLevel(100.0, 30.0), BookLevel(101.0, 25.0), BookLevel(102.0, 15.0)),
)
depth = depth_from_snapshot(book)
side = combine_pressure(
    depth_pressure_side(depth.imbalance),
    rise_pressure_side(0.08),
)
feats = feature_vector(book, prior_ask=99.5, prior_bid=98.5)
```

## Map to Julie / study cortex

- Mesh: `brain/mesh/repos.yaml` entry `sgx-orderbook`
- Spine: `brain/spine/Algorithms.md`
- Curriculum: `bridge-sgx-depth-rise`
- Catalog: [docs/help.md](../help.md)

## Upstream layout (cheat sheet)

```
SGX-.../Data_Transformation/   raw LOB CSV → train/test builders
SGX-.../Feature_Selection/     rise ratio + depth feature notebooks
SGX-.../Model_Selection/       sklearn grid / rolling CV / P&L plots
SGX-.../Graph/                 pipeline + prediction figures
```

AOA agents should read the notebooks for feature ideas; they should not treat
the 2014 SGX sample CSVs as live market data or wire them into `aoa loop`.
