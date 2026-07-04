#!/usr/bin/env bash
# Write OpenStock/.env from AOA .env + openstock.env.example defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOA_ENV_FILE="${AOA_ENV_FILE:-$ROOT/.env}"
OPENSTOCK_ENV="${OPENSTOCK_ENV:-$ROOT/OpenStock/.env}"
TEMPLATE="${OPENSTOCK_TEMPLATE:-$ROOT/openstock.env.example}"

if [[ ! -d "$ROOT/OpenStock" ]]; then
  echo "OpenStock directory missing. Run ./scripts/openstock-setup.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1090
read_env() {
  local key="$1"
  local file="$2"
  if [[ -f "$file" ]]; then
    grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2- || true
  fi
}

cp "$TEMPLATE" "$OPENSTOCK_ENV"

finnhub="$(read_env FINNHUB_API_KEY "$AOA_ENV_FILE")"
if [[ -z "$finnhub" ]]; then
  finnhub="$(read_env NEXT_PUBLIC_FINNHUB_API_KEY "$AOA_ENV_FILE")"
fi
if [[ -n "$finnhub" ]]; then
  if grep -q '^NEXT_PUBLIC_FINNHUB_API_KEY=' "$OPENSTOCK_ENV"; then
    sed -i "s|^NEXT_PUBLIC_FINNHUB_API_KEY=.*|NEXT_PUBLIC_FINNHUB_API_KEY=${finnhub}|" "$OPENSTOCK_ENV"
  else
    echo "NEXT_PUBLIC_FINNHUB_API_KEY=${finnhub}" >>"$OPENSTOCK_ENV"
  fi
fi

gemini="$(read_env GEMINI_API_KEY "$AOA_ENV_FILE")"
if [[ -n "$gemini" ]] && grep -q '^GEMINI_API_KEY=' "$OPENSTOCK_ENV"; then
  sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=${gemini}|" "$OPENSTOCK_ENV"
fi

if ! grep -q '^BETTER_AUTH_SECRET=change-me' "$OPENSTOCK_ENV" 2>/dev/null; then
  :
elif command -v openssl >/dev/null 2>&1; then
  secret="$(openssl rand -hex 32)"
  sed -i "s|^BETTER_AUTH_SECRET=.*|BETTER_AUTH_SECRET=${secret}|" "$OPENSTOCK_ENV"
fi

echo "Wrote $OPENSTOCK_ENV"
if [[ -z "$finnhub" ]]; then
  echo "Note: set FINNHUB_API_KEY in $AOA_ENV_FILE or NEXT_PUBLIC_FINNHUB_API_KEY in OpenStock/.env"
fi
