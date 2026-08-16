#!/usr/bin/env bash
# Clone optional companion workspaces beside AOA (idempotent).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

run() {
  local label="$1" script="$2"
  if [[ -x "$script" ]]; then
    echo "==> $label"
    "$script" || echo "WARN: $script exited non-zero (continuing)"
  else
    echo "SKIP: missing $script"
  fi
}

run "OpenStock" "./scripts/openstock-setup.sh"
run "QM" "./scripts/qm-setup.sh"
run "VisualHFT (+ oxyplot)" "./scripts/visualhft-setup.sh"
run "example-hftish" "./scripts/example-hftish-setup.sh"
run "open-quant-live-book" "./scripts/open-quant-live-book-setup.sh"

echo ""
echo "==> Refresh multi-root workspace file"
./scripts/write-aoa-workspace.sh

echo ""
echo "==> Mesh status"
python3 -m aoa.cli workspaces status || true

echo ""
echo "Done. Open AOA.code-workspace in Cursor. Desktop VisualHFT still needs Windows/.NET 10."
echo "Positions/Orders empty tab: see docs/how-to/visualhft-positions-orders.md"
