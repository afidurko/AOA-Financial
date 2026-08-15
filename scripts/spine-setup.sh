#!/usr/bin/env bash
# Clone Spine beside the repo and link Cursor skills.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPINE_DIR="${SPINE_DIR:-$ROOT/spine}"
SPINE_REPO="${SPINE_REPO:-https://github.com/afidurko/spine.git}"
CURSOR_SKILLS="$ROOT/.cursor/skills"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

git_clone_if_missing "$SPINE_DIR" "$SPINE_REPO" "Spine"

linked="$(link_cursor_skills "$SPINE_DIR" "$CURSOR_SKILLS")"
echo "Linked $linked Spine skills into $CURSOR_SKILLS"

if [[ -x "$ROOT/scripts/sync-spine-config.sh" ]]; then
  AOA_OBSIDIAN_VAULT_PATH="$VAULT_DIR" "$ROOT/scripts/sync-spine-config.sh"
fi

echo ""
echo "Spine ready."
echo "  Repo:   $SPINE_DIR"
echo "  Skills: spine-init, spine-capture, spine-health, spine-scan, spine-update, spine-recall"
echo ""
echo "Next: run ./scripts/integrate-spine-obsidian.sh to wire Spine with obsidian-second-brain"
