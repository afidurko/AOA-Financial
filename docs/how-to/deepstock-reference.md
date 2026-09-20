# deepstock reference

[afidurko/deepstock](https://github.com/afidurko/deepstock) is the original
deep-learning stock-market experiment repo. AOA Financial keeps it as an
**optional sibling reference** — same pattern as `hft` and
`open-quant-live-book` — not as a live order or inference path.

## What is in the sibling

| Path | Status | Notes |
|------|--------|-------|
| `news-analysis/` | Prototype | Kim (2014) Text CNN on headlines; TensorFlow 1.x; saved checkpoint under `save/checkpoints/` |
| `stock-analysis/convnet/` | Partial | Price-window ConvNet; references missing `bn_class.py` |
| RNN / DQN bot, multi-feature, portfolio, macro | Planned | Not implemented in upstream |

Upstream targets **TensorFlow 0.8+ / 1.x** (`tensorflow.contrib`, `tf.flags`).
Expect a port (PyTorch or TF 2.x) before running on a modern stack.

## What AOA uses instead

| deepstock idea | AOA landing |
|----------------|-------------|
| News headline sentiment | `aoa_financial/analysis/sentiment.py` — small lexicon scorer (offline, auditable) |
| Forecast / backtest | `aoa_financial/` factor models, regimes, walk-forward engine |
| Live trading | `src/aoa/` swarm via Moomoo / Alpaca with deterministic guardrails |

There is no `aoa.research.deepstock_patterns` module yet; deepstock is
archival context for future CNN / NLP ports.

## Safety (Hard Floor)

- Do **not** vendor or run deepstock training/inference from an AOA loop.
- Do **not** set `AOA_ENV=live` or submit live orders from deepstock code.
- Treat saved TF1 checkpoints as research artifacts only.

## Clone beside the repo

```bash
./scripts/deepstock-setup.sh
# or: DEEPSTOCK_DIR=/path/to/deepstock DEEPSTOCK_REPO=https://github.com/afidurko/deepstock.git ./scripts/deepstock-setup.sh
```

The sibling directory `deepstock/` is gitignored.

Refresh the multi-root workspace after cloning:

```bash
./scripts/write-aoa-workspace.sh
```

## Mesh

- Machine-readable: `brain/mesh/repos.yaml` entry `deepstock`
- Vault note: `vault/system/deepstock.md`
