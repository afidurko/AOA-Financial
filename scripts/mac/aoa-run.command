#!/usr/bin/env bash
# One analysis cycle (paper-dry = no orders). Double-click in Finder.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run aoa-setup.command first."
  read -r -p "Press Enter to close..."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if ! nc -z 127.0.0.1 11111 2>/dev/null; then
  echo "✗ OpenD not running — open Moomoo OpenD first."
  read -r -p "Press Enter to close..."
  exit 1
fi

echo "=== aoa run (paper-dry — analyzes only, no orders) ==="
python -m aoa.cli run || true
echo
read -r -p "Press Enter to close..."
