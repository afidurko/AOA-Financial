#!/usr/bin/env bash
# Ensure .env has knowledge-stack variables (idempotent).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${AOA_ENV_FILE:-$ROOT/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example"
fi

ensure_line() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    key="$key" value="$value" awk -v key="$key" -v val="$value" '
      BEGIN { done = 0 }
      $0 ~ "^" key "=" { print key "=" val; done = 1; next }
      { print }
      END { if (!done) print key "=" val }
    ' "$ENV_FILE" >"$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
  else
    echo "${key}=${value}" >>"$ENV_FILE"
  fi
}

ensure_line "AOA_OBSIDIAN_VAULT_PATH" "./AOA-Vault"
ensure_line "AOA_SPINE_ENABLED" "true"
echo "Knowledge-stack lines present in $ENV_FILE"
