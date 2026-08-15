#!/usr/bin/env bash
# Clone the example-hftish sibling beside the repo (not vendored, not run by AOA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE_HFTISH_DIR="${EXAMPLE_HFTISH_DIR:-$ROOT/example-hftish}"
EXAMPLE_HFTISH_REPO="${EXAMPLE_HFTISH_REPO:-https://github.com/afidurko/example-hftish.git}"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

if [[ -e "$EXAMPLE_HFTISH_DIR" && ! -d "$EXAMPLE_HFTISH_DIR/.git" ]]; then
  echo "error: $EXAMPLE_HFTISH_DIR exists but is not a git clone; remove or set EXAMPLE_HFTISH_DIR elsewhere" >&2
  exit 1
fi

git_clone_if_missing "$EXAMPLE_HFTISH_DIR" "$EXAMPLE_HFTISH_REPO" "example-hftish"

echo ""
echo "example-hftish sibling ready (reference only — not started, not linked to AOA orders)."
echo "  Docs: docs/how-to/example-hftish-reference.md"
echo "  Python patterns: python3 -c 'from aoa.research import hftish_patterns'"
echo "  Upstream is Alpaca tick_taker (Polygon stream + submit_order); do not run it from AOA loops."
echo "  Safety: paper/research use only; never wire companion API keys into AOA live paths."
