# VisualHFT microstructure integration

AOA Financial wraps study formulas from
[afidurko/VisualHFT](https://github.com/afidurko/VisualHFT)
(fork of [visualHFT/VisualHFT](https://github.com/visualHFT/VisualHFT)) as an
**offline Python research lane** for market-microstructure metrics.

It does **not** replace:

- the VisualHFT Windows/.NET 10 WPF desktop app (live L2 dashboard + plugins)
- `aoa hft` / `aoa.hftbacktest` — tick-level L2/L3 backtest engine
- `aoa simulate` / `aoa.simulation` — bar Monte-Carlo and scenario stress
- live paper/live execution — never submit orders from this path

## Install

No extra pip dependency — the research lane is pure Python (stdlib only).

Desktop VisualHFT (Windows):

```powershell
# Both repositories must sit in the same parent folder.
git clone https://github.com/visualHFT/oxyplot.git
git clone https://github.com/afidurko/VisualHFT.git
# Open VisualHFT/VisualHFT.sln in Visual Studio (.NET 10), F5
```

## Commands

```bash
aoa visualhft status
aoa visualhft studies
aoa visualhft studies --ported-only --json
aoa visualhft smoke
aoa visualhft smoke --trades 200 --seed 1 --json
```

`status` / `studies` describe the fork and which formulas are ported.
`smoke` runs LOB imbalance, VPIN, and order-to-trade ratio on a synthetic tape
(no venue sockets, no orders).

## Library API

```python
from aoa.visualhft import probe_status, run_synthetic_smoke
from aoa.visualhft.studies import lob_imbalance, order_to_trade_ratio, VPINState, TradePrint

print(probe_status())
print(lob_imbalance([12, 8], [5, 5], book_depth=2))
print(run_synthetic_smoke(n_trades=100, seed=1).to_dict())
```

## Ported studies

| Study | Formula source | Notes |
|-------|----------------|-------|
| LOB Imbalance | `OrderFlowAnalysis.Calculate_OrderImbalance` | Top-N size imbalance ∈ [-1, 1] |
| VPIN | `VPINStudy` | Volume buckets + rolling mean of \|buy−sell\|/bucket |
| Order-to-Trade Ratio | `OrderToTradeRatioStudy` (L2 mode) | `(add+del+2×upd)/max(trades,1) − 1` |
| Market Resilience | desktop plugin | Not ported yet — use WPF host |

## Complementary lanes

| Lane | Role |
|------|------|
| VisualHFT desktop | Live crypto L2 books, tiles, triggers, REST alerts |
| `aoa visualhft` | Offline Python ports of study math for AOA research |
| `aoa hft` | Optional hftbacktest tick replay (when that PR/extra is installed) |

## Safety

- Offline research only (`offline_only` / `never_live` in status JSON)
- Not wired into `Executor`, swarm stages, or `AOA_ENV=live`
- Hard safety floor still applies: no live order submission from loops
- VisualHFT REST trigger payloads may be pointed at a local AOA webhook later;
  this package does not auto-execute trades from alerts
