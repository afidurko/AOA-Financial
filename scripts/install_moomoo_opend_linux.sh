#!/usr/bin/env bash
# Install Moomoo command-line OpenD on Linux (Ubuntu/CentOS).
# Official docs: https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html
#
# Usage:
#   bash scripts/install_moomoo_opend_linux.sh [install_dir]
#
# After download, configure OpenD.xml and start:
#   cd <install_dir>/OpenD && nohup ./OpenD &
set -euo pipefail

INSTALL_DIR="${1:-$HOME/moomoo-opend}"
DOC_URL="https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html"
DOWNLOAD_URL="https://www.moomoo.com/download/OpenAPI"

ok() { printf '\033[0;32m✓\033[0m %s\n' "$*"; }
need() { printf '\033[0;31m→ YOU:\033[0m %s\n' "$*"; }

echo "=== Moomoo OpenD — Linux install helper ==="
echo

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "Use scripts/install_moomoo_opend_macos.sh on macOS." >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
ok "Install directory: $INSTALL_DIR"

echo
need "Download command-line OpenD for your distro from:"
echo "       $DOWNLOAD_URL"
echo "       (see also: $DOC_URL)"
echo
need "Extract the archive into: $INSTALL_DIR"
need "Edit OpenD.xml — set login_account, login_pwd, api_port=11111"
need "Start OpenD:"
echo "       cd $INSTALL_DIR/OpenD && nohup ./OpenD &"
echo

HOST="${MOOMOO_OPEND_HOST:-127.0.0.1}"
PORT="${MOOMOO_OPEND_PORT:-11111}"
if python3 - <<PY 2>/dev/null
import socket
s = socket.socket()
s.settimeout(2)
s.connect(("${HOST}", int("${PORT}")))
s.close()
PY
then
  ok "OpenD already reachable at ${HOST}:${PORT}"
else
  need "OpenD not yet listening on ${HOST}:${PORT}"
fi

echo
echo "Optional — unofficial Docker (not Moomoo-supported):"
echo "  cp docker-compose.moomoo-opend.example.yml docker-compose.moomoo-opend.yml"
echo "  # edit credentials, then: docker compose -f docker-compose.moomoo-opend.yml up -d"
echo
echo "From AOA repo after OpenD is up:"
echo "  aoa setup moomoo && aoa doctor && aoa run"
