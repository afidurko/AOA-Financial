#!/usr/bin/env bash
# Write ~/.config/obsidian-second-brain/.env from AOA .env + template defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOA_ENV_FILE="${AOA_ENV_FILE:-$ROOT/.env}"
OSB_CONFIG_DIR="${OBSIDIAN_SECONDBRAIN_CONFIG:-$HOME/.config/obsidian-second-brain}"
OSB_ENV="${OBSIDIAN_SECONDBRAIN_ENV:-$OSB_CONFIG_DIR/.env}"
TEMPLATE="${OBSIDIAN_SECONDBRAIN_TEMPLATE:-$ROOT/obsidian-second-brain.env.example}"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"

# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh"

mkdir -p "$OSB_CONFIG_DIR"
cp "$TEMPLATE" "$OSB_ENV"
chmod 600 "$OSB_ENV"

env_upsert OBSIDIAN_VAULT_PATH "$VAULT_DIR" "$OSB_ENV"

for key in GEMINI_API_KEY PERPLEXITY_API_KEY XAI_API_KEY YOUTUBE_API_KEY; do
  val="$(env_read "$key" "$AOA_ENV_FILE")"
  [[ -n "$val" ]] && env_upsert "$key" "$val" "$OSB_ENV"
done

chmod 600 "$OSB_ENV"
echo "Wrote $OSB_ENV"
if [[ -z "$(env_read OBSIDIAN_VAULT_PATH "$OSB_ENV")" ]]; then
  echo "Note: set AOA_OBSIDIAN_VAULT_PATH in $AOA_ENV_FILE or OBSIDIAN_VAULT_PATH in $OSB_ENV"
fi
