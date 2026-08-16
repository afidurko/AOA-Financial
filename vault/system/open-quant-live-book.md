---
type: system-companion
name: open-quant-live-book
enabled: true
setup: scripts/open-quant-live-book-setup.sh
docs: docs/how-to/open-quant-live-book-reference.md
repo: https://github.com/afidurko/open-quant-live-book
module: aoa.research.open_quant_patterns
locked: []
---
# open-quant-live-book — quant finance book reference

Optional sibling. Fork of souzatharsis/open-quant-live-book (risk parity,
entropy, transfer entropy). Clone with `./scripts/open-quant-live-book-setup.sh`.
Use `aoa.research.open_quant_patterns` for pure-Python idea ports. AOA remains
the only order path; never wire book R scripts here.
