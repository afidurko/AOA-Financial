#!/usr/bin/env bash
# Write OpenStock/.env from AOA .env + openstock.env.example defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOA_ENV_FILE="${AOA_ENV_FILE:-$ROOT/.env}"
OPENSTOCK_ENV="${OPENSTOCK_ENV:-$ROOT/OpenStock/.env}"
TEMPLATE="${OPENSTOCK_TEMPLATE:-$ROOT/openstock.env.example}"

# shellcheck source=scripts/lib/env-file.sh
source "$ROOT/scripts/lib/env-file.sh"

if [[ ! -d "$ROOT/OpenStock" ]]; then
  echo "OpenStock directory missing. Run ./scripts/openstock-setup.sh first." >&2
  exit 1
fi

cp "$TEMPLATE" "$OPENSTOCK_ENV"

finnhub="$(env_read FINNHUB_API_KEY "$AOA_ENV_FILE")"
[[ -n "$finnhub" ]] || finnhub="$(env_read NEXT_PUBLIC_FINNHUB_API_KEY "$AOA_ENV_FILE")"
[[ -n "$finnhub" ]] && env_upsert NEXT_PUBLIC_FINNHUB_API_KEY "$finnhub" "$OPENSTOCK_ENV"

gemini="$(env_read GEMINI_API_KEY "$AOA_ENV_FILE")"
[[ -n "$gemini" ]] && env_upsert GEMINI_API_KEY "$gemini" "$OPENSTOCK_ENV"

# Replace the placeholder auth secret with a real one (leave custom values alone).
if [[ "$(env_read BETTER_AUTH_SECRET "$OPENSTOCK_ENV")" == "change-me" ]] && command -v openssl >/dev/null 2>&1; then
  env_upsert BETTER_AUTH_SECRET "$(openssl rand -hex 32)" "$OPENSTOCK_ENV"
fi

echo "Wrote $OPENSTOCK_ENV"
if [[ -z "$finnhub" ]]; then
  echo "Note: set FINNHUB_API_KEY in $AOA_ENV_FILE or NEXT_PUBLIC_FINNHUB_API_KEY in OpenStock/.env"
fi
