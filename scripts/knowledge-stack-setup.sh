#!/usr/bin/env bash
# One-command setup: obsidian-second-brain + Spine + shared vault bridge + AOA wiring.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Knowledge stack setup (obsidian-second-brain + Spine + AOA) =="
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
echo ""
echo "== Knowledge stack ready =="
echo ""
echo "Add to .env:"
echo "  AOA_OBSIDIAN_VAULT_PATH=$VAULT_DIR"
echo "  AOA_SPINE_ENABLED=true"
echo ""
echo "Workflow:"
echo "  1. Open $VAULT_DIR in Obsidian"
echo "  2. /obsidian-init  — obsidian-second-brain vault manual (uses obsidian-skills for format)"
echo "  3. /obsidian-architect — document AOA codebase (OSB)"
echo "  4. /spine-capture — after commits, draft feature docs (Spine)"
echo "  5. aoa serve — trading dashboard with Second Brain link"
