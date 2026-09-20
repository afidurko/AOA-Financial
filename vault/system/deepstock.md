---
type: system-companion
name: deepstock
enabled: true
setup: scripts/deepstock-setup.sh
docs: docs/how-to/deepstock-reference.md
repo: https://github.com/afidurko/deepstock
locked: []
---
# deepstock — legacy deep-learning experiments

Optional sibling. Original TF1 prototypes for news Text CNN (headline → DJIA
correlation) and price ConvNet classification. Clone with
`./scripts/deepstock-setup.sh`. AOA sentiment today lives in
`aoa_financial/analysis/sentiment.py` (lexicon). Reference only — never an AOA
order path.
