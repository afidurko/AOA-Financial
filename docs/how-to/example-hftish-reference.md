# Example HFT-ish (order-book imbalance) reference

[afidurko/example-hftish](https://github.com/afidurko/example-hftish) is a fork of
[alpacahq/example-hftish](https://github.com/alpacahq/example-hftish): Alpaca's
streaming tick-taker that follows large prints after 1¢ bid/ask level changes when
the book is imbalanced. AOA Financial keeps it as an **optional sibling reference**
— same pattern as AutoHedge / FinancePy / qm — not as a live order path.

## What AOA takes from it

| Upstream piece | Idea | AOA landing |
|----------------|------|-------------|
| `Quote.update` | Both bid and ask move onto a new 1¢ spread → “level change” | `detect_level_change`, `arms_after_level_change` |
| Bid/ask size gate | Trade only when one side is ≥ 1.8× the other | `book_imbalance_side`, `imbalance_ratio` |
| `on_trade` follow | Large print (≥100) hits ask/bid after ≥50ms lag | `follow_print_signal`, `trade_follows_quote` |
| `Position` caps | Cap inventory / pending lots (100-share lots) | `position_allows_buy`, `position_allows_sell` |
| `submit_order` / StreamConn | Live Alpaca + Polygon path | **Not wired** |

AOA stays bar-based (Alpaca / Moomoo equities & cash options). There is no
Polygon quote stream and no IOC tick-taker in this repo.

## Safety (Hard Floor)

- Do **not** run `tick_taker.py` from an AOA loop or repair worktree.
- Do **not** put companion Alpaca keys in `.env`, `brain/`, or `vault/`.
- Do **not** set `AOA_ENV=live` or submit live orders from example-hftish code.
- Python helpers in `aoa.research.hftish_patterns` never call a broker.

## Clone beside the repo

```bash
./scripts/example-hftish-setup.sh
# or: EXAMPLE_HFTISH_DIR=/path/to/example-hftish \
#     EXAMPLE_HFTISH_REPO=https://github.com/afidurko/example-hftish.git \
#     ./scripts/example-hftish-setup.sh
```

The sibling directory `example-hftish/` is gitignored.

## Use the Python patterns

```python
from aoa.research.hftish_patterns import (
    TopOfBook,
    detect_level_change,
    follow_print_signal,
)

prev = TopOfBook(10.00, 10.01, bid_size=200, ask_size=100, timestamp_ms=0)
curr = TopOfBook(10.01, 10.02, bid_size=500, ask_size=100, timestamp_ms=100)
change = detect_level_change(prev, curr)
sig = follow_print_signal(
    curr,
    trade_price=10.02,
    trade_size=100,
    trade_timestamp_ms=200,
    armed=True,
)  # research signal only — never an AOA order
```

## Map to Julie / study cortex

- Mesh: `brain/mesh/repos.yaml` entry `example-hftish`
- Spine: `brain/spine/Algorithms.md`
- Curriculum: `bridge-hftish-imbalance` (book pressure ↔ level-change follow)
- Catalog: [docs/help.md](../help.md)

## Upstream layout (cheat sheet)

```
example-hftish/tick_taker.py   Quote + Position + StreamConn handlers
example-hftish/Pipfile         alpaca-trade-api dependency pin
example-hftish/README.md       PDT warning, SNAP default, Polygon note
```

Upstream requires a live Alpaca account for Polygon streaming historically.
AOA agents should read the strategy for microstructure ideas; they should not
execute that script from a cloud loop.
