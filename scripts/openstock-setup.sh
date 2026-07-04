#!/usr/bin/env bash
# Clone OpenStock beside the repo if missing and prepare a local .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENSTOCK_DIR="${OPENSTOCK_DIR:-$ROOT/OpenStock}"
OPENSTOCK_REPO="${OPENSTOCK_REPO:-https://github.com/Open-Dev-Society/OpenStock.git}"

if [[ ! -d "$OPENSTOCK_DIR/.git" ]]; then
  echo "Cloning OpenStock into $OPENSTOCK_DIR"
  git clone "$OPENSTOCK_REPO" "$OPENSTOCK_DIR"
else
  echo "OpenStock already present at $OPENSTOCK_DIR"
fi

if [[ ! -f "$OPENSTOCK_DIR/.env" ]]; then
  if [[ -x "$ROOT/scripts/sync-openstock-env.sh" ]]; then
    "$ROOT/scripts/sync-openstock-env.sh"
  else
    cp "$ROOT/openstock.env.example" "$OPENSTOCK_DIR/.env"
    echo "Created $OPENSTOCK_DIR/.env from openstock.env.example"
  fi
fi

if command -v npm >/dev/null 2>&1; then
  echo "Installing OpenStock npm dependencies…"
  (cd "$OPENSTOCK_DIR" && npm install)
else
  echo "npm not found — skip npm install"
fi

echo ""
echo "OpenStock ready."
echo "  cd OpenStock && npm run dev     # http://localhost:3000"
echo "  export AOA_OPENSTOCK_URL=http://localhost:3000 && aoa serve"
