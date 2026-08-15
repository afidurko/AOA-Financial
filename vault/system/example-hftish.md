---
type: system-companion
name: example-hftish
enabled: true
setup: scripts/example-hftish-setup.sh
docs: docs/how-to/example-hftish-reference.md
repo: https://github.com/afidurko/example-hftish
module: aoa.research.hftish_patterns
locked: []
---
# example-hftish — order-book imbalance reference

Optional sibling. Fork of alpacahq/example-hftish (Alpaca tick_taker). Clone with
`./scripts/example-hftish-setup.sh`. Use `aoa.research.hftish_patterns` for
pure-Python idea ports. Julie and Morgan consume `diagnose_snapshot_quote` as
research-only book hints; CLI: `aoa hftish status|smoke`. AOA remains the only
order path; never run tick_taker from loops.
