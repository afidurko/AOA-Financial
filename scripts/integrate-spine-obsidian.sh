#!/usr/bin/env bash
# Install Spine bridge into obsidian-second-brain and wire shared vault.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OSB_DIR="${OBSIDIAN_SECONDBRAIN_DIR:-$ROOT/obsidian-second-brain}"
BRIDGE_SRC="$ROOT/bridge/spine-obsidian"
BRIDGE_DST="$OSB_DIR/integrations/spine"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"

if [[ ! -d "$OSB_DIR" ]]; then
  echo "obsidian-second-brain missing at $OSB_DIR — run ./scripts/obsidian-second-brain-setup.sh first." >&2
  exit 1
fi

if [[ ! -d "$BRIDGE_SRC" ]]; then
  echo "Bridge templates missing at $BRIDGE_SRC" >&2
  exit 1
fi

mkdir -p "$OSB_DIR/integrations"
rm -rf "$BRIDGE_DST"
mkdir -p "$BRIDGE_DST"
cp "$BRIDGE_SRC/README.md" "$BRIDGE_SRC/setup.sh" "$BRIDGE_SRC/graph.json" \
   "$BRIDGE_SRC/spine-architecture.md" "$BRIDGE_DST/"
chmod +x "$BRIDGE_DST/setup.sh"
echo "Installed bridge → $BRIDGE_DST"

AOA_ROOT="$ROOT" AOA_OBSIDIAN_VAULT_PATH="$VAULT_DIR" bash "$BRIDGE_DST/setup.sh"
