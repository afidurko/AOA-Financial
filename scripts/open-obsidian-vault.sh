#!/usr/bin/env bash
# Open AOA-Vault in Obsidian (macOS) or print the path.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}"

if [[ -f "$ROOT/.env" ]]; then
  val="$(grep -E '^AOA_OBSIDIAN_VAULT_PATH=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if [[ -n "$val" ]]; then
    if [[ "$val" = /* ]]; then
      VAULT_DIR="$val"
    else
      VAULT_DIR="$ROOT/$val"
    fi
  fi
fi

if [[ ! -d "$VAULT_DIR" ]]; then
  echo "Vault not found at $VAULT_DIR — run ./scripts/knowledge-stack-setup.sh first." >&2
  exit 1
fi

VAULT_DIR="$(cd "$VAULT_DIR" && pwd)"
VAULT_NAME="$(basename "$VAULT_DIR")"

if [[ "$(uname -s)" == Darwin ]]; then
  if open -a Obsidian "$VAULT_DIR" 2>/dev/null; then
    echo "Opened $VAULT_DIR in Obsidian"
    exit 0
  fi
  if open "obsidian://open?vault=${VAULT_NAME}" 2>/dev/null; then
    echo "Launched Obsidian URI for vault: $VAULT_NAME"
    exit 0
  fi
fi

echo "Open this folder as a vault in Obsidian:"
echo "  $VAULT_DIR"
