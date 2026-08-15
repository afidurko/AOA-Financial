# HFT backtest (hftbacktest) integration

AOA Financial wraps [afidurko/hftbacktest](https://github.com/afidurko/hftbacktest)
(fork of [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest)) as an
**optional offline** tick-level L2/L3 backtest lane.

It does **not** replace:

- `aoa simulate` / `aoa.simulation` — bar Monte-Carlo and scenario stress
- `aoa_financial` walk-forward backtest — daily decision harness
- live paper/live execution — never submit orders from this path

## Install

```bash
pip install -e ".[hftbacktest]"
```

PyPI wheels are used by default. The tracked research fork is
`https://github.com/afidurko/hftbacktest`.

## Commands

```bash
aoa hft status
aoa hft smoke
aoa hft smoke --events 500 --steps 30 --seed 1 --json
aoa hft run path/to/feed.npz --tick-size 0.01 --lot-size 0.001
```

`status` / `smoke` verify the optional dependency and Numba engine with a
synthetic depth tape (no external tick files, no orders).

`run` advances time on an on-disk hftbacktest feed prepared with the upstream
data utilities (Binance, Bybit, Tardis, …). It only probes the book — it does
not place live or paper orders.

## Library API

```python
from aoa.hftbacktest import HAS_HFTBACKTEST, probe_status, run_npz_smoke

print(probe_status())
if HAS_HFTBACKTEST:
    print(run_npz_smoke(n_events=200, steps=10).to_dict())
```

## Safety

- Offline research only (`offline_only: true` in status JSON)
- Not wired into `Executor`, swarm stages, or `AOA_ENV=live`
- Hard safety floor still applies: no live order submission from loops
