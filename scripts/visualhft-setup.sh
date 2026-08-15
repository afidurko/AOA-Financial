#!/usr/bin/env bash
# Clone VisualHFT (+ oxyplot sibling) beside the repo if missing.
# Upstream requires VisualHFT and oxyplot in the same parent folder.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VISUALHFT_DIR="${VISUALHFT_DIR:-$ROOT/VisualHFT}"
VISUALHFT_REPO="${VISUALHFT_REPO:-https://github.com/afidurko/VisualHFT.git}"
OXYPLOT_REPO="${OXYPLOT_REPO:-https://github.com/visualHFT/oxyplot.git}"

if [[ ! -d "$VISUALHFT_DIR/.git" ]]; then
  echo "Cloning VisualHFT into $VISUALHFT_DIR"
  git clone "$VISUALHFT_REPO" "$VISUALHFT_DIR"
else
  echo "VisualHFT already present at $VISUALHFT_DIR"
fi

OXY_PARENT="$(cd "$(dirname "$VISUALHFT_DIR")" && pwd)"
OXYPLOT_DIR="${OXYPLOT_DIR:-$OXY_PARENT/oxyplot}"

if [[ ! -d "$OXYPLOT_DIR/.git" ]]; then
  echo "Cloning VisualHFT oxyplot fork into $OXYPLOT_DIR"
  git clone "$OXYPLOT_REPO" "$OXYPLOT_DIR"
else
  echo "oxyplot already present at $OXYPLOT_DIR"
fi

echo ""
echo "VisualHFT sibling ready (Windows/.NET 10 desktop — not started here)."
echo "  Open $VISUALHFT_DIR/VisualHFT.sln in Visual Studio and press F5"
echo "  export AOA_VISUALHFT_URL=https://github.com/afidurko/VisualHFT"
echo "  aoa visualhft status   # Python research lane (LOB / VPIN / OTR)"
echo "  aoa workspaces status  # mesh with OpenStock / QM / hftbacktest"
echo "  Docs: docs/how-to/visualhft-integration.md"
