#!/usr/bin/env bash
# One-shot macOS bootstrap: Python 3.10+, venv, pip install, .env scaffold.
#
# Usage (from repo root, no prior install required):
#   bash scripts/setup_mac.sh
#   bash scripts/setup_mac.sh --moomoo   # also run Moomoo/OpenD checks after install
#
# Re-run safe: reuses .venv if Python >= 3.10; recreates if too old.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_MOOMOO=0
for arg in "$@"; do
  case "$arg" in
    --moomoo) RUN_MOOMOO=1 ;;
    -h|--help)
      echo "Usage: bash scripts/setup_mac.sh [--moomoo]"
      echo "  Bootstraps Python 3.10+, .venv, pip install -e \".[dev,web]\", and .env"
      exit 0
      ;;
  esac
done

ok() { printf '\033[0;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
need() { printf '\033[0;31m→ YOU:\033[0m %s\n' "$*"; }

MIN_PY_MAJOR=3
MIN_PY_MINOR=10
VENV="$ROOT/.venv"
EXTRAS="${AOA_SETUP_EXTRAS:-dev,web}"

echo "=== AOA Financial — macOS bootstrap ==="
echo "Repo: $ROOT"
echo

if [[ "$(uname -s)" != "Darwin" ]]; then
  warn "This script targets macOS. On Linux use: pip install -e \".[dev,web]\" with Python 3.10+"
fi

_py_version_ok() {
  "$1" -c "import sys; raise SystemExit(0 if sys.version_info >= (${MIN_PY_MAJOR}, ${MIN_PY_MINOR}) else 1)" 2>/dev/null
}

_find_python() {
  local cmd candidates=()
  if command -v brew >/dev/null 2>&1; then
    local prefix
    for formula in python@3.12 python@3.11 python@3.10; do
      prefix="$(brew --prefix "$formula" 2>/dev/null || true)"
      if [[ -n "$prefix" && -x "$prefix/bin/python3" ]]; then
        candidates+=("$prefix/bin/python3")
      fi
    done
  fi
  for cmd in python3.12 python3.11 python3.10 python3; do
    candidates+=("$cmd")
  done
  local c
  for c in "${candidates[@]}"; do
    if command -v "$c" >/dev/null 2>&1 && _py_version_ok "$c"; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

_install_python_brew() {
  if ! command -v brew >/dev/null 2>&1; then
    need "Install Homebrew first:"
    echo "       /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo "       Then re-run: bash scripts/setup_mac.sh"
    return 1
  fi
  warn "Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR} not found — installing python@3.12 via Homebrew…"
  brew install python@3.12
}

PYTHON=""
if ! PYTHON="$(_find_python)"; then
  _install_python_brew || exit 1
  PYTHON="$(_find_python)" || {
    need "Could not find Python 3.10+ after brew install. Try: brew install python@3.12"
    exit 1
  }
fi

VER="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.micro}")')"
ok "Using $PYTHON ($VER)"

_recreate_venv=0
if [[ -d "$VENV" ]]; then
  if "$VENV/bin/python" -c "import sys; raise SystemExit(0 if sys.version_info >= (${MIN_PY_MAJOR}, ${MIN_PY_MINOR}) else 1)" 2>/dev/null; then
    ok "Existing .venv is Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR}"
  else
    warn "Removing .venv (Python too old — e.g. macOS system 3.9)"
    _recreate_venv=1
  fi
fi

if [[ ! -d "$VENV" || "$_recreate_venv" -eq 1 ]]; then
  [[ "$_recreate_venv" -eq 1 ]] && rm -rf "$VENV"
  "$PYTHON" -m venv "$VENV"
  ok "Created virtualenv at .venv"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

ok "Activated .venv ($(python3 --version))"

python3 -m pip install --upgrade pip setuptools wheel -q
ok "pip / setuptools / wheel upgraded"

echo "Installing aoa-financial [.${EXTRAS}] (may take a minute)…"
python3 -m pip install -e ".[${EXTRAS}]" -q
ok "Package installed"

if [[ ! -f .env ]]; then
  cp .env.example .env
  ok "Created .env from .env.example"
  need "Edit .env — set ANTHROPIC_API_KEY=sk-ant-..."
else
  ok ".env exists"
fi

if command -v aoa >/dev/null 2>&1; then
  ok "aoa CLI available: $(command -v aoa)"
else
  ok "aoa via: python3 -m aoa.cli"
fi

echo
echo "=== Next steps ==="
echo "Every new Terminal window:"
echo "  cd $ROOT"
echo "  source .venv/bin/activate"
echo
echo "Then:"
echo "  aoa setup moomoo    # OpenD checks"
echo "  aoa doctor"
echo "  aoa run"
echo

if [[ "$RUN_MOOMOO" -eq 1 ]]; then
  echo "=== Moomoo setup ==="
  bash "$ROOT/scripts/setup_moomoo_auth.sh" || true
fi

python3 -m aoa.cli doctor --offline 2>/dev/null || true
