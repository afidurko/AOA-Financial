#!/usr/bin/env bash
# One-command setup: obsidian-second-brain + Spine + shared vault bridge + AOA wiring.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Knowledge stack setup (obsidian-second-brain + Spine + AOA) =="
echo ""

"$ROOT/scripts/ensure-knowledge-stack-env.sh"
echo ""

"$ROOT/scripts/obsidian-second-brain-setup.sh"
echo ""
"$ROOT/scripts/spine-setup.sh"
echo ""
"$ROOT/scripts/integrate-spine-obsidian.sh"
echo ""
"$ROOT/scripts/obsidian-skills-setup.sh"
echo ""
"$ROOT/scripts/integrate-obsidian-skills.sh"

VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"
if [[ -f "$ROOT/.env" ]]; then
  val="$(grep -E '^AOA_OBSIDIAN_VAULT_PATH=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if [[ -n "$val" ]]; then
    if [[ "$val" = /* ]]; then VAULT_DIR="$val"; else VAULT_DIR="$ROOT/$val"; fi
  fi
fi

echo ""
"$ROOT/scripts/verify-knowledge-stack.sh" || true
echo ""
"$ROOT/scripts/open-obsidian-vault.sh" || true
echo ""
echo "== Knowledge stack ready =="
echo ""
echo ".env updated with:"
echo "  AOA_OBSIDIAN_VAULT_PATH=./AOA-Vault"
echo "  AOA_SPINE_ENABLED=true"
echo ""
echo "Automated: clones, .env lines, vault, bridges, verification, open Obsidian (macOS)"
echo ""
echo "Manual (cannot automate):"
echo "  1. Restart Cursor (loads MCP + skills)"
echo "  2. /obsidian-init and /obsidian-architect in Cursor chat"
echo "  3. aoa serve (needs API keys in .env — see SETUP-AWAITING-YOU.md)"
