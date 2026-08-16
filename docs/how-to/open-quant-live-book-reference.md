# Open Quant Live Book reference

[afidurko/open-quant-live-book](https://github.com/afidurko/open-quant-live-book)
is a fork of
[souzatharsis/open-quant-live-book](https://github.com/souzatharsis/open-quant-live-book):
an open, reproducible bookdown project covering financial data analysis, algo
trading, portfolio selection, econophysics, and ML in finance.

AOA Financial keeps it as an **optional sibling reference** — same pattern as
`hft` / `example-hftish` / SGX — not as a live order path. The book itself is
R/bookdown; AOA does not build or vendor it.

## What AOA takes from it

| Upstream chapter | Idea | AOA landing |
|------------------|------|-------------|
| `RiskParity/` | Equal risk contribution / risk-budget portfolios | `equal_risk_contribution`, `inverse_vol_weights`, `risk_contributions` (+ `risk_fractions`) |
| `Entropy/` | Shannon entropy, mutual information, global correlation λ | `shannon_entropy`, `mutual_information_stats` |
| `TransferEntropy/` | Linear Granger causality + Gaussian TE = GC/2; net flow | `linear_granger_causality`, `net_information_flow`, `coupled_ar_series` |
| StylizedFacts / LimitOrder / ML parts | Mostly stubs or narrative | Stay in the sibling — **not** ported |

AOA stays bar-based (Alpaca / Moomoo equities & cash options). There is no
bookdown/R runtime in this repo and no automatic rebalance from these helpers
into `Executor`.

## Safety (Hard Floor)

- Do **not** vendor or auto-build the sibling book from an AOA loop.
- Do **not** put exchange credentials in `.env`, `brain/`, or `vault/`.
- Do **not** set `AOA_ENV=live` or submit live orders from open-quant research code.
- Python helpers in `aoa.research.open_quant_patterns` never call a broker.

## Clone beside the repo

```bash
./scripts/open-quant-live-book-setup.sh
# or: OQLB_DIR=/path/to/sibling OQLB_REPO=https://github.com/afidurko/open-quant-live-book.git ./scripts/open-quant-live-book-setup.sh
```

The sibling directory `open-quant-live-book/` is gitignored.

## Use the Python patterns

```python
from aoa.research.open_quant_patterns import (
    equal_risk_contribution,
    inverse_vol_weights,
    mutual_information_stats,
    net_information_flow,
)

inv = inverse_vol_weights((0.20, 0.10))
erc = equal_risk_contribution([[0.04, 0.0], [0.0, 0.01]])
mi = mutual_information_stats([0.1, -0.2, 0.05, 0.0], [0.08, -0.1, 0.02, 0.01])
flow = net_information_flow(list(range(50)), [0.5 * i for i in range(50)], lags=1)
```

CLI: `aoa openquant status|smoke`. Smoke: `python3 examples/open_quant_smoke.py`.

## Map to Julie / study cortex

- Mesh: `brain/mesh/repos.yaml` entry `open-quant-live-book`
- Spine: `brain/spine/Algorithms.md`
- Curriculum: `bridge-oqlb-risk-entropy`
- Catalog: [docs/help.md](../help.md)

## Upstream layout (cheat sheet)

```
open-quant-live-book/chapters/RiskParity/       ERC vs tangency (FAANG)
open-quant-live-book/chapters/Entropy/          Shannon / MI / λ
open-quant-live-book/chapters/TransferEntropy/ Granger + TE + net flow
open-quant-live-book/chapters/StylizedFacts/   stubs
open-quant-live-book/data/                     sample CSVs for the book
```

AOA agents should read chapters for portfolio / information-theory ideas; they
should not compile the PDF or treat FAANG notebook returns as live market data.
