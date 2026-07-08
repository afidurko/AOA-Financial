#!/usr/bin/env bash
# Write ~/.config/obsidian-second-brain/.env from AOA .env + template defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOA_ENV_FILE="${AOA_ENV_FILE:-$ROOT/.env}"
OSB_CONFIG_DIR="${OBSIDIAN_SECONDBRAIN_CONFIG:-$HOME/.config/obsidian-second-brain}"
OSB_ENV="${OBSIDIAN_SECONDBRAIN_ENV:-$OSB_CONFIG_DIR/.env}"
TEMPLATE="${OBSIDIAN_SECONDBRAIN_TEMPLATE:-$ROOT/obsidian-second-brain.env.example}"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"

# shellcheck disable=SC1090
read_env() {
  local key="$1"
  local file="$2"
  if [[ -f "$file" ]]; then
    grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2- || true
  fi
}

write_env() {
  local key="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    return
  fi
  # awk is portable on macOS (BSD sed -i requires a backup extension).
  key="$key" value="$value" awk -v key="$key" -v val="$value" '
    BEGIN { done = 0 }
    $0 ~ "^" key "=" { print key "=" val; done = 1; next }
    { print }
    END { if (!done) print key "=" val }
  ' "$OSB_ENV" >"$OSB_ENV.tmp" && mv "$OSB_ENV.tmp" "$OSB_ENV"
}

mkdir -p "$OSB_CONFIG_DIR"
cp "$TEMPLATE" "$OSB_ENV"
chmod 600 "$OSB_ENV"

write_env OBSIDIAN_VAULT_PATH "$VAULT_DIR"

for key in GEMINI_API_KEY PERPLEXITY_API_KEY XAI_API_KEY YOUTUBE_API_KEY; do
  val="$(read_env "$key" "$AOA_ENV_FILE")"
  write_env "$key" "$val"
done

echo "Wrote $OSB_ENV"
if [[ -z "$(read_env OBSIDIAN_VAULT_PATH "$OSB_ENV")" ]]; then
  echo "Note: set AOA_OBSIDIAN_VAULT_PATH in $AOA_ENV_FILE or OBSIDIAN_VAULT_PATH in $OSB_ENV"
fi
