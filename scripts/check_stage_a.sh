#!/usr/bin/env bash
# Stage A verification — run on your Mac from the AOA repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY=""
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PY="$(command -v python3.12)"
else
  PY="$(command -v python3)"
fi

echo "=== Stage A check ==="
echo "Project: $ROOT"
echo "Python:  $PY ($("$PY" --version 2>&1))"
echo

ok() { printf '  ✓ %s\n' "$*"; }
fail() { printf '  ✗ %s\n' "$*"; }

PASS=0
FAIL=0
note() { printf '  · %s\n' "$*"; }

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  ok "Virtual env .venv exists"
  PASS=$((PASS + 1))
else
  fail "No .venv — run: python3.12 -m venv .venv && source .venv/bin/activate"
  FAIL=$((FAIL + 1))
fi

if "$PY" -c "import aoa" 2>/dev/null; then
  ok "aoa package importable"
  PASS=$((PASS + 1))
else
  fail "aoa not installed — run: source .venv/bin/activate && pip install -e \".[dev,web]\""
  FAIL=$((FAIL + 1))
fi

if [[ -f .env ]]; then
  ok ".env exists"
  PASS=$((PASS + 1))
else
  fail "Missing .env — run: cp .env.example .env"
  FAIL=$((FAIL + 1))
fi

if nc -z 127.0.0.1 11111 2>/dev/null; then
  ok "OpenD reachable on 127.0.0.1:11111"
  PASS=$((PASS + 1))
else
  fail "OpenD not reachable — start Moomoo OpenD app and log in"
  FAIL=$((FAIL + 1))
fi

echo
echo "=== aoa doctor ==="
if "$PY" -m aoa.cli doctor; then
  echo
  ok "Stage A COMPLETE — live data works, no orders (paper-dry)"
else
  echo
  fail "doctor failed — see errors above"
  exit 1
fi
