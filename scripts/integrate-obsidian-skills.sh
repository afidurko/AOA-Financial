#!/usr/bin/env bash
# Install obsidian-skills bridge into obsidian-second-brain and vault.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OSB_DIR="${OBSIDIAN_SECONDBRAIN_DIR:-$ROOT/obsidian-second-brain}"
BRIDGE_SRC="$ROOT/bridge/obsidian-skills"
BRIDGE_DST="$OSB_DIR/integrations/obsidian-skills"

if [[ ! -d "$OSB_DIR" ]]; then
  echo "obsidian-second-brain missing — run ./scripts/obsidian-second-brain-setup.sh first." >&2
  exit 1
fi

if [[ ! -d "${OBSIDIAN_SKILLS_DIR:-$ROOT/obsidian-skills}" ]]; then
  echo "obsidian-skills missing — run ./scripts/obsidian-skills-setup.sh first." >&2
  exit 1
fi

mkdir -p "$OSB_DIR/integrations"
rm -rf "$BRIDGE_DST"
mkdir -p "$BRIDGE_DST"
cp "$BRIDGE_SRC/README.md" "$BRIDGE_SRC/setup.sh" "$BRIDGE_SRC/claude-md-snippet.md" "$BRIDGE_DST/"
chmod +x "$BRIDGE_DST/setup.sh"
echo "Installed bridge → $BRIDGE_DST"

AOA_ROOT="$ROOT" bash "$BRIDGE_DST/setup.sh"
