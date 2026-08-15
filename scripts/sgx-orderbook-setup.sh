#!/usr/bin/env bash
# Clone the SGX full-order-book ML strategy sibling beside the repo
# (not vendored, not run by AOA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SGX_DIR="${SGX_DIR:-$ROOT/SGX-Full-OrderBook-Tick-Data-Trading-Strategy}"
SGX_REPO="${SGX_REPO:-https://github.com/afidurko/SGX-Full-OrderBook-Tick-Data-Trading-Strategy.git}"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

if [[ -e "$SGX_DIR" && ! -d "$SGX_DIR/.git" ]]; then
  echo "error: $SGX_DIR exists but is not a git clone; remove or set SGX_DIR elsewhere" >&2
  exit 1
fi

git_clone_if_missing "$SGX_DIR" "$SGX_REPO" "SGX order-book"

echo ""
echo "SGX sibling ready (reference only — notebooks not executed by AOA)."
echo "  Docs: docs/how-to/sgx-orderbook-reference.md"
echo "  Python patterns: python3 -c 'from aoa.research import sgx_orderbook_patterns'"
echo "  Upstream is SGX A50 tick notebooks (rise/depth/sklearn); no broker wiring."
echo "  Safety: paper/research use only; never wire exchange credentials into AOA."
