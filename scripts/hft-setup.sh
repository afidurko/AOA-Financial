#!/usr/bin/env bash
# Clone the HFT C++ reference sibling beside the repo (not vendored, not run by AOA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HFT_DIR="${HFT_DIR:-$ROOT/hft}"
HFT_REPO="${HFT_REPO:-https://github.com/afidurko/hft.git}"

if [[ ! -d "$HFT_DIR/.git" ]]; then
  echo "Cloning HFT reference into $HFT_DIR"
  git clone "$HFT_REPO" "$HFT_DIR"
else
  echo "HFT already present at $HFT_DIR"
fi

echo ""
echo "HFT sibling ready (reference only — not started, not linked to AOA orders)."
echo "  Docs: docs/how-to/hft-reference.md"
echo "  Python patterns: python3 -c 'from aoa.research import hft_patterns'"
echo "  Upstream is CentOS/CTP/ZeroMQ C++; do not point AOA brokers at it."
echo "  Safety: paper/research use only; never wire CTP credentials into AOA."
