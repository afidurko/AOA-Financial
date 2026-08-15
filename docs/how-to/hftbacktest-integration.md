# HFT backtest (hftbacktest) integration

AOA Financial can wrap [afidurko/hftbacktest](https://github.com/afidurko/hftbacktest)
(fork of [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest)) as an
**optional offline** tick-level L2/L3 backtest lane.

> Status: optional extra / companion PR. Until `aoa.hftbacktest` is installed,
> `aoa workspaces status` reports it as unlinked. See also
> [workspaces.md](workspaces.md) and [visualhft-integration.md](visualhft-integration.md).

## Install (when available)

```bash
pip install -e ".[hftbacktest]"
aoa hft status
aoa hft smoke
```

## Safety

- Offline research only — never submit live or paper orders from this path
- Complementary to `aoa visualhft` (study formulas) and VisualHFT desktop (live L2 UI)
