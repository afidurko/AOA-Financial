#!/usr/bin/env bash
# Clone Spine beside the repo and link Cursor skills.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPINE_DIR="${SPINE_DIR:-$ROOT/spine}"
SPINE_REPO="${SPINE_REPO:-https://github.com/afidurko/spine.git}"
CURSOR_SKILLS="$ROOT/.cursor/skills"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"

if [[ ! -d "$SPINE_DIR/.git" ]]; then
  echo "Cloning Spine into $SPINE_DIR"
  git clone "$SPINE_REPO" "$SPINE_DIR"
else
  echo "Spine already present at $SPINE_DIR"
fi

mkdir -p "$CURSOR_SKILLS"
linked=0
for skill_dir in "$SPINE_DIR"/skills/*/; do
  [[ -d "$skill_dir" ]] || continue
  name="$(basename "$skill_dir")"
  dest="$CURSOR_SKILLS/$name"
  ln -snf "$skill_dir" "$dest"
  linked=$((linked + 1))
done
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
