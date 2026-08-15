#!/usr/bin/env bash
# Moomoo + AOA setup helper — prints only the human steps.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ok() { printf '\033[0;32m✓\033[0m %s\n' "$*"; }
need() { printf '\033[0;31m→ YOU:\033[0m %s\n' "$*"; }

echo "=== AOA Financial — Moomoo setup ==="
echo "(CLI: aoa setup moomoo)"
echo

if [[ ! -f .env ]]; then
  cp .env.example .env
  ok "Created .env from .env.example"
else
  ok ".env exists"
fi

if ! python3 -c "import aoa" 2>/dev/null; then
  need 'Run: pip install -e ".[dev]"'
else
  ok "Python package aoa importable"
fi

if python3 -c "import moomoo" 2>/dev/null; then
  ok "moomoo-api installed"
else
  need 'Run: pip install moomoo-api  (or pip install -e ".[dev]")'
fi

if grep -qE '^AOA_LLM_PROVIDER=openai_compatible[[:space:]]*$' .env 2>/dev/null \
  && grep -qE '^AOA_LLM_BASE_URL=https?://[^[:space:]]+' .env 2>/dev/null; then
  ok "Local LLM (WASTE / openai_compatible) configured in .env"
elif grep -q '^ANTHROPIC_API_KEY=sk-' .env 2>/dev/null; then
  ok "ANTHROPIC_API_KEY looks set (opt-in Claude provider)"
else
  need "Start WASTE serve and keep AOA_LLM_PROVIDER=openai_compatible — docs/how-to/waste-local-llm.md"
fi

HOST="${MOOMOO_OPEND_HOST:-127.0.0.1}"
PORT="${MOOMOO_OPEND_PORT:-11111}"
if python3 - <<PY 2>/dev/null
import socket
s = socket.socket()
s.settimeout(2)
s.connect(("${HOST}", int("${PORT}")))
s.close()
print("ok")
PY
then
  ok "OpenD reachable at ${HOST}:${PORT}"
else
  echo
  need "Install and start Moomoo OpenD — https://www.moomoo.com/download/OpenAPI/"
  echo "       Agent skill: /install-moomoo-opend (Cursor/Claude)"
  echo "       macOS: bash scripts/install_moomoo_opend_macos.sh"
  echo "       Linux: bash scripts/install_moomoo_opend_linux.sh"
  echo "       Log in with your Moomoo account. Default port: 11111"
  echo
fi

echo
echo "=== Config check ==="
python3 -m aoa.cli doctor --offline || true

if python3 - <<PY 2>/dev/null
import socket
s = socket.socket(); s.settimeout(2); s.connect(("${HOST}", int("${PORT}"))); s.close()
PY
then
  echo
  python3 -m aoa.cli doctor || true
else
  echo
  echo "Skipping live doctor until OpenD is running."
fi

echo
echo "Full checklist: SETUP-AWAITING-YOU.md"
