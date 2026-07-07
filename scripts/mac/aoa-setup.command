#!/usr/bin/env bash
# One-time setup: Python venv + AOA install. Double-click in Finder.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "=== AOA Financial — one-time setup ==="
echo "Project: $ROOT"
echo

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install from https://brew.sh first, then run this again."
  read -r -p "Press Enter to close..."
  exit 1
fi

PY=""
for candidate in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3.12; do
  if [[ -x "$candidate" ]] && "$candidate" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done

if [[ -z "$PY" ]]; then
  echo "Python 3.10+ not found. Installing python@3.12 via Homebrew..."
  brew install python@3.12
  PY="/opt/homebrew/bin/python3.12"
  [[ -x "$PY" ]] || PY="/usr/local/bin/python3.12"
fi

echo "Using: $PY ($("$PY" --version))"
echo

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment .venv ..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,web]"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — opening in TextEdit. Add ANTHROPIC_API_KEY=sk-ant-..."
  open -e .env
fi

python -c "import aoa; print('✓ aoa installed OK')"
echo
echo "Setup done. Next:"
echo "  1. Edit .env in TextEdit (Anthropic key)"
echo "  2. Open Moomoo OpenD and log in"
echo "  3. Double-click scripts/mac/aoa-doctor.command"
echo
read -r -p "Press Enter to close..."
