#!/usr/bin/env bash
# Clone the deepstock sibling beside the repo (not vendored, not run by AOA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEEPSTOCK_DIR="${DEEPSTOCK_DIR:-$ROOT/deepstock}"
DEEPSTOCK_REPO="${DEEPSTOCK_REPO:-https://github.com/afidurko/deepstock.git}"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

if [[ -e "$DEEPSTOCK_DIR" && ! -d "$DEEPSTOCK_DIR/.git" ]]; then
  echo "error: $DEEPSTOCK_DIR exists but is not a git clone; remove or set DEEPSTOCK_DIR elsewhere" >&2
  exit 1
fi

git_clone_if_missing "$DEEPSTOCK_DIR" "$DEEPSTOCK_REPO" "deepstock"

echo ""
echo "deepstock sibling ready (reference only — not started, not linked to AOA orders)."
echo "  Docs: docs/how-to/deepstock-reference.md"
echo "  Legacy TF1 experiments: news Text CNN + price ConvNet prototypes."
echo "  AOA sentiment today: aoa_financial/analysis/sentiment.py (lexicon, offline)."
echo "  Safety: research use only; never wire deepstock training/inference into live loops."
