#!/usr/bin/env bash
# Write ~/.spine/config.json from AOA .env (shared vault with obsidian-second-brain).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPINE_CONFIG="${SPINE_CONFIG:-$HOME/.spine/config.json}"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"
TIER3="${AOA_SPINE_TIER3:-true}"
AUTOLOAD="${AOA_SPINE_AUTOLOAD:-true}"

mkdir -p "$(dirname "$SPINE_CONFIG")"
cat >"$SPINE_CONFIG" <<EOF
{
  "vaultPath": "$VAULT_DIR",
  "tier3": $TIER3,
  "autoLoad": $AUTOLOAD
}
EOF
chmod 600 "$SPINE_CONFIG" 2>/dev/null || true
echo "Wrote $SPINE_CONFIG (vaultPath=$VAULT_DIR)"
