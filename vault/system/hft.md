---
type: system-companion
name: hft
enabled: true
setup: scripts/hft-setup.sh
docs: docs/how-to/hft-reference.md
repo: https://github.com/afidurko/hft
module: aoa.research.hft_patterns
locked: []
---
# HFT — C++ strategy reference

Optional sibling. Fork of keyianpai/hft (CTP/ZeroMQ futures HFT). Clone with
`./scripts/hft-setup.sh`. Use `aoa.research.hft_patterns` for pure-Python idea
ports. AOA remains the only order path; never wire CTP credentials here.
