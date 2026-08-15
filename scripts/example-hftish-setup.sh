#!/usr/bin/env bash
# Clone the example-hftish sibling beside the repo (not vendored, not run by AOA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE_HFTISH_DIR="${EXAMPLE_HFTISH_DIR:-$ROOT/example-hftish}"
EXAMPLE_HFTISH_REPO="${EXAMPLE_HFTISH_REPO:-https://github.com/afidurko/example-hftish.git}"

if [[ ! -d "$EXAMPLE_HFTISH_DIR/.git" ]]; then
  echo "Cloning example-hftish reference into $EXAMPLE_HFTISH_DIR"
  git clone "$EXAMPLE_HFTISH_REPO" "$EXAMPLE_HFTISH_DIR"
else
  echo "example-hftish already present at $EXAMPLE_HFTISH_DIR"
fi

echo ""
echo "example-hftish sibling ready (reference only — not started, not linked to AOA orders)."
echo "  Docs: docs/how-to/example-hftish-reference.md"
echo "  Python patterns: python3 -c 'from aoa.research import hftish_patterns'"
echo "  Upstream is Alpaca tick_taker (Polygon stream + submit_order); do not run it from AOA loops."
echo "  Safety: paper/research use only; never wire companion API keys into AOA live paths."
