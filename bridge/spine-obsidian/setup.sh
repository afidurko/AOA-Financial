#!/usr/bin/env bash
# Wire Spine and obsidian-second-brain to the same Obsidian vault.
# Installed to obsidian-second-brain/integrations/spine/ by AOA setup.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OSB_ROOT="$(cd "$HERE/../.." && pwd)"
ROOT="${AOA_ROOT:-$(cd "$OSB_ROOT/.." 2>/dev/null && pwd || echo "$OSB_ROOT/..")}"

VAULT_DIR="${AOA_OBSIDIAN_VAULT_PATH:-${OBSIDIAN_VAULT_PATH:-$ROOT/AOA-Vault}}"
SPINE_CONFIG="${SPINE_CONFIG:-$HOME/.spine/config.json}"
REPO_NAME="${SPINE_REPO_NAME:-AOA-Financial}"

green() { printf '\033[0;32m%s\033[0m\n' "$1"; }

if [[ ! -d "$VAULT_DIR" ]]; then
  echo "Vault missing at $VAULT_DIR — run obsidian-second-brain setup first." >&2
  exit 1
fi

mkdir -p "$HOME/.spine"
mkdir -p "$VAULT_DIR/.spine"
mkdir -p "$VAULT_DIR/.obsidian"
mkdir -p "$VAULT_DIR/$REPO_NAME"

# Shared config: Spine reads vaultPath; OSB reads OBSIDIAN_VAULT_PATH
cat >"$SPINE_CONFIG" <<EOF
{
  "vaultPath": "$VAULT_DIR",
  "tier3": true,
  "autoLoad": true
}
EOF
chmod 600 "$SPINE_CONFIG" 2>/dev/null || true
green "Wrote $SPINE_CONFIG"

OSB_ENV="${OBSIDIAN_SECONDBRAIN_ENV:-$HOME/.config/obsidian-second-brain/.env}"
mkdir -p "$(dirname "$OSB_ENV")"
if [[ -f "$OSB_ENV" ]]; then
  VAULT_DIR="$VAULT_DIR" awk '
    /^OBSIDIAN_VAULT_PATH=/ { print "OBSIDIAN_VAULT_PATH=" ENVIRON["VAULT_DIR"]; done=1; next }
    { print }
    END { if (!done) print "OBSIDIAN_VAULT_PATH=" ENVIRON["VAULT_DIR"] }
  ' "$OSB_ENV" >"$OSB_ENV.tmp" && mv "$OSB_ENV.tmp" "$OSB_ENV"
else
  echo "OBSIDIAN_VAULT_PATH=$VAULT_DIR" >"$OSB_ENV"
  chmod 600 "$OSB_ENV"
fi
green "Synced OBSIDIAN_VAULT_PATH in $OSB_ENV"

# Spine graph colors + meta doc (idempotent)
if [[ -f "$HERE/graph.json" ]]; then
  cp "$HERE/graph.json" "$VAULT_DIR/.obsidian/graph.json"
elif [[ -d "$ROOT/spine/templates" ]]; then
  cp "$ROOT/spine/templates/graph.json" "$VAULT_DIR/.obsidian/graph.json"
fi

if [[ ! -f "$VAULT_DIR/Spine Architecture.md" ]]; then
  if [[ -f "$HERE/spine-architecture.md" ]]; then
    cp "$HERE/spine-architecture.md" "$VAULT_DIR/Spine Architecture.md"
  elif [[ -f "$ROOT/spine/templates/spine-architecture.md" ]]; then
    cp "$ROOT/spine/templates/spine-architecture.md" "$VAULT_DIR/Spine Architecture.md"
  fi
fi

if [[ -f "$ROOT/spine/templates/retrieval-policy.md" ]]; then
  cp "$ROOT/spine/templates/retrieval-policy.md" "$VAULT_DIR/.spine/retrieval-policy.md"
fi

write_spine_note() {
  local feature="$1"
  local desc="$2"
  local dir="$VAULT_DIR/$REPO_NAME/$feature"
  local note="$dir/$feature.md"
  [[ -f "$note" ]] && return 0
  mkdir -p "$dir"
  local slug
  slug="$(echo "$feature" | tr '[:upper:]' '[:lower:]')"
  cat >"$note" <<EOF
---
title: $feature — $REPO_NAME
tags:
  - $REPO_NAME
  - $slug
  - type/spine
---

# $feature ($REPO_NAME)

$desc

## Fixes

## Features

## Architecture

## Plans

## Decisions
EOF
  green "  Created spine note: $feature"
}

write_spine_note "Swarm" "Autonomous trading team orchestration, agent roles, and cycle execution."
write_spine_note "Broker" "Broker connectivity (Moomoo OpenD, Alpaca), order execution, and account state."
write_spine_note "Work-loop" "Loop engineering, triage, repair gate, and workloop automation."

# Cross-link note for agents (additive; OSB _CLAUDE.md remains authoritative for OSB)
BRIDGE_NOTE="$VAULT_DIR/.spine/spine-obsidian-bridge.md"
cat >"$BRIDGE_NOTE" <<EOF
---
tags:
  - type/meta
  - integration
---

# Spine + obsidian-second-brain bridge

This vault is shared by **Spine** (feature docs under \`$REPO_NAME/\`) and
**obsidian-second-brain** (AI-first notes under \`Daily/\`, \`Projects/\`, etc.).

- Use \`/spine-capture\` after commits to draft feature docs.
- Use \`/obsidian-save\` and \`/obsidian-ingest\` for session capture and research.
- Use \`/obsidian-architect\` for codebase architecture; \`/spine-recall\` for feature deep pulls.
EOF
green "Wrote $BRIDGE_NOTE"

echo ""
green "Spine ↔ obsidian-second-brain bridge ready."
echo "  Vault:       $VAULT_DIR"
echo "  Spine config: $SPINE_CONFIG"
echo "  Repo folder:  $VAULT_DIR/$REPO_NAME/"
