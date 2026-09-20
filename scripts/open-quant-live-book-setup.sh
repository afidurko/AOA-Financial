#!/usr/bin/env bash
# Clone the open-quant-live-book sibling beside the repo (not vendored, not run by AOA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OQLB_DIR="${OQLB_DIR:-$ROOT/open-quant-live-book}"
OQLB_REPO="${OQLB_REPO:-https://github.com/afidurko/open-quant-live-book.git}"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

if [[ -e "$OQLB_DIR" && ! -d "$OQLB_DIR/.git" ]]; then
  echo "error: $OQLB_DIR exists but is not a git clone; remove or set OQLB_DIR elsewhere" >&2
  exit 1
fi

git_clone_if_missing "$OQLB_DIR" "$OQLB_REPO" "open-quant-live-book"

echo ""
echo "open-quant-live-book sibling ready (reference only — not started, not linked to AOA orders)."
echo "  Docs: docs/how-to/open-quant-live-book-reference.md"
echo "  Python patterns: python3 -c 'from aoa.research import open_quant_patterns'"
echo "  CLI: aoa openquant status|smoke"
echo "  Upstream is R/bookdown; do not build the book from an AOA loop."
echo "  Safety: paper/research use only; never wire book scripts into Executor."
