# Avellaneda–Stoikov market-making integration

AOA Financial wraps the simulation math from
[afidurko/avellaneda-stoikov](https://github.com/afidurko/avellaneda-stoikov)
(Avellaneda & Stoikov, *High-frequency trading in a limit order book*, 2008) as an
**offline Python research lane** for reservation-price market making.

It does **not** replace:

- `aoa simulate` / `aoa.simulation` — bar Monte-Carlo and scenario stress
- `aoa.hftbacktest` / `aoa.orderbook` — tick L2 lanes (sibling integrations)
- live paper/live execution — never submit orders from this path

## Install

No extra pip dependency — the research lane is pure Python (stdlib only).

Upstream reference (plots / papers):

```bash
git clone https://github.com/afidurko/avellaneda-stoikov.git
cd avellaneda-stoikov/src && pip install -r requirements.txt
# python main.py  # matplotlib interactive demo
```

## Commands

```bash
aoa avellaneda status
aoa avellaneda smoke
aoa avellaneda smoke --steps 200 --sims 20 --seed 1 --json
aoa avellaneda simulate --steps 200 --seed 1 --json
aoa avellaneda simulate --ensemble --sims 50 --seed 1 --json
```

`status` describes the lane. `smoke` checks reservation quotes + a short
ensemble. `simulate` runs one path (or an ensemble with `--ensemble`).

## Library API

```python
from aoa.avellaneda_stoikov import (
    ASParams,
    limited_horizon_quotes,
    probe_status,
    run_simulation,
    run_synthetic_smoke,
)
from aoa.avellaneda_stoikov.simulate import SimConfig

print(probe_status())
params = ASParams(gamma=0.1, sigma=2.0, k=1.5, T=1.0)
quotes = limited_horizon_quotes(mid=100.0, inventory=2.0, t=0.0, params=params)
print(quotes.reservation, quotes.bid, quotes.ask)
print(run_simulation(SimConfig(n_steps=200, seed=1, params=params)).final_pnl)
print(run_synthetic_smoke(n_steps=100, n_sims=10, seed=1).to_dict())
```

## Formulas (limited horizon)

| Quantity | Formula |
|----------|---------|
| Reservation price | `r = s − q γ σ² (T − t)` |
| Reservation spread | `(2/γ) log(1 + γ/k)` |
| Ask / bid | `r ± spread/2` |
| Arrival intensity | `λ = A exp(−k δ)` |
| Fill probability | `1 − exp(−λ dt)` |

Unlimited-horizon quotes (inventory-bound) are also available via
`unlimited_horizon_quotes`.

## Complementary lanes

| Lane | Role |
|------|------|
| Upstream `avellaneda-stoikov` | Matplotlib demo + paper PDFs |
| `aoa avellaneda` | Headless Python ports for AOA research / study cortex |
| `aoa visualhft` | LOB imbalance / VPIN / OTR studies |
| `aoa hft` | Optional tick backtest / vendored LOB |
| `aoa microstructure status` | Mesh catalog for every offline HFT/LOB lane |

See [microstructure-lanes.md](microstructure-lanes.md).

## Safety

- Offline research only (`offline_only` / `never_live` in status JSON)
- Not wired into `Executor`, swarm stages, or `AOA_ENV=live`
- Hard safety floor still applies: no live order submission from loops
- Cash-account AOA swarm remains bar-based equities/options — AS is study/reference
