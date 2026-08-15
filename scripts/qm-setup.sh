#!/usr/bin/env bash
# Clone QM beside the repo if missing and print local run hints.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QM_DIR="${QM_DIR:-$ROOT/qm}"
QM_REPO="${QM_REPO:-https://github.com/afidurko/qm.git}"
QM_PORT="${QM_PORT:-8081}"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh"

git_clone_if_missing "$QM_DIR" "$QM_REPO" "QM"

if [[ ! -f "$QM_DIR/.env" && -f "$QM_DIR/.env.example" ]]; then
  cp "$QM_DIR/.env.example" "$QM_DIR/.env"
  env_upsert PORT "$QM_PORT" "$QM_DIR/.env"
  echo "Created $QM_DIR/.env from .env.example (PORT=${QM_PORT})"
fi

if command -v npm >/dev/null 2>&1; then
  echo "Installing QM npm dependencies…"
  (cd "$QM_DIR" && npm install)
else
  echo "npm not found — skip npm install"
fi

echo ""
echo "QM sibling ready (not started)."
echo "  QM needs Node >= 24, Postgres, and org deploy config — see docs/how-to/qm-integration.md"
echo "  cd qm && npm run dev          # core HTTP (default PORT from .env)"
echo "  export AOA_QM_URL=http://localhost:${QM_PORT} && aoa serve"
echo "  Dashboard header shows QM ↗ when AOA_QM_URL is set."
