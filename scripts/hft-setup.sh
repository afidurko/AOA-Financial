#!/usr/bin/env bash
# Clone the HFT C++ reference sibling beside the repo (not vendored, not run by AOA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HFT_DIR="${HFT_DIR:-$ROOT/hft}"
HFT_REPO="${HFT_REPO:-https://github.com/afidurko/hft.git}"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

if [[ -e "$HFT_DIR" && ! -d "$HFT_DIR/.git" ]]; then
  echo "error: $HFT_DIR exists but is not a git clone; remove or set HFT_DIR elsewhere" >&2
  exit 1
fi

git_clone_if_missing "$HFT_DIR" "$HFT_REPO" "HFT"

echo ""
echo "HFT sibling ready (reference only — not started, not linked to AOA orders)."
echo "  Docs: docs/how-to/hft-reference.md"
echo "  Python patterns: python3 -c 'from aoa.research import hft_patterns'"
echo "  Offline L2 backtest (separate): docs/how-to/hftbacktest-integration.md"
echo "  Upstream is CentOS/CTP/ZeroMQ C++; do not point AOA brokers at it."
echo "  Safety: paper/research use only; never wire CTP credentials into AOA."
