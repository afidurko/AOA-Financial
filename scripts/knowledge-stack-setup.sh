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
echo ""
"$ROOT/scripts/integrate-moomoo-skills.sh"

echo ""
if ! "$ROOT/scripts/verify-knowledge-stack.sh"; then
  echo ""
  echo "== Knowledge stack VERIFY FAILED ==" >&2
  echo "Fix the checks above, then re-run ./scripts/knowledge-stack-setup.sh" >&2
  exit 1
fi
echo ""
"$ROOT/scripts/write-aoa-workspace.sh"
echo ""
"$ROOT/scripts/open-obsidian-vault.sh" || true
echo ""
echo "== Knowledge stack ready =="
echo ""
echo ".env updated with:"
echo "  AOA_OBSIDIAN_VAULT_PATH=./AOA-Vault"
echo "  AOA_SPINE_ENABLED=true"
echo ""
echo "Automated: clones, .env lines, vault, bridges, Moomoo skills check,"
echo "  AOA.code-workspace, verification, open Obsidian (macOS)"
echo ""
echo "Manual (cannot automate):"
echo "  1. Open AOA.code-workspace in Cursor (multi-root workspaces)"
echo "  2. Restart Cursor (loads MCP + skills)"
echo "  3. /obsidian-init and /obsidian-architect in Cursor chat"
echo "  4. aoa serve (needs API keys in .env — see SETUP-AWAITING-YOU.md)"
echo "     Or always-on: ./scripts/setup-always-on.sh (LaunchAgent + Tailscale)"
echo "  5. Moomoo: /install-moomoo-opend (local) then /moomooapi for quotes/orders"
