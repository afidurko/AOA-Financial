#!/usr/bin/env bash
# Ensure .env has knowledge-stack variables (idempotent).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${AOA_ENV_FILE:-$ROOT/.env}"

# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example"
fi

env_upsert "AOA_OBSIDIAN_VAULT_PATH" "./AOA-Vault" "$ENV_FILE"
env_upsert "AOA_SPINE_ENABLED" "true" "$ENV_FILE"
echo "Knowledge-stack lines present in $ENV_FILE"
