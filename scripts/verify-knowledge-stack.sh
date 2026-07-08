#!/usr/bin/env bash
# Verify knowledge stack installation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"
# Resolve relative vault path from .env
if [[ -f "$ROOT/.env" ]]; then
  val="$(grep -E '^AOA_OBSIDIAN_VAULT_PATH=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if [[ -n "$val" ]]; then
    if [[ "$val" = /* ]]; then
      VAULT_DIR="$val"
    else
      VAULT_DIR="$(cd "$ROOT/$val" && pwd)"
    fi
  fi
fi

pass=0
fail=0

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  ✓ $name"
    pass=$((pass + 1))
  else
    echo "  ✗ $name"
    fail=$((fail + 1))
  fi
}

echo "Knowledge stack verification"
echo "  Root:  $ROOT"
echo "  Vault: $VAULT_DIR"
echo ""

check ".env exists" test -f "$ROOT/.env"
check "AOA_OBSIDIAN_VAULT_PATH in .env" grep -q '^AOA_OBSIDIAN_VAULT_PATH=' "$ROOT/.env"
check "AOA_SPINE_ENABLED in .env" grep -q '^AOA_SPINE_ENABLED=true' "$ROOT/.env"
check "AOA-Vault exists" test -d "$VAULT_DIR"
check "Vault _CLAUDE.md" test -f "$VAULT_DIR/_CLAUDE.md"
check "obsidian-second-brain clone" test -d "$ROOT/obsidian-second-brain/.git"
check "spine clone" test -d "$ROOT/spine/.git"
check "obsidian-skills clone" test -d "$ROOT/obsidian-skills/.git"
check "OSB spine bridge" test -f "$ROOT/obsidian-second-brain/integrations/spine/setup.sh"
check "OSB skills bridge" test -f "$ROOT/obsidian-second-brain/integrations/obsidian-skills/setup.sh"
check "Cursor MCP config" test -f "$ROOT/.cursor/mcp.json"
check "Cursor skill obsidian-second-brain" test -e "$ROOT/.cursor/skills/obsidian-second-brain"

echo ""
echo "Result: $pass passed, $fail failed"
if [[ "$fail" -gt 0 ]]; then
  echo "Run: ./scripts/knowledge-stack-setup.sh"
  exit 1
fi
echo "Knowledge stack OK."
