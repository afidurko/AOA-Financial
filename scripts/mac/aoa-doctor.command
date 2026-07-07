#!/usr/bin/env bash
# Health check: OpenD + broker + API key. Double-click in Finder.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run aoa-setup.command first (one-time setup)."
  read -r -p "Press Enter to close..."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "=== OpenD port 11111 ==="
if nc -z 127.0.0.1 11111 2>/dev/null; then
  echo "✓ OpenD reachable"
else
  echo "✗ OpenD not running — open Moomoo OpenD app and log in, then run this again."
  read -r -p "Press Enter to close..."
  exit 1
fi

echo
echo "=== aoa doctor ==="
python -m aoa.cli doctor || true
echo
read -r -p "Press Enter to close..."
